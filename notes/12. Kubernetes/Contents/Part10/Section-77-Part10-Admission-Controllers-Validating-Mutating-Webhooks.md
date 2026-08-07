# Section 77 (Part 10): Admission Controllers: Validating and Mutating Webhooks

## 1. Definition

**Plain language:** Authentication ([§73](./Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md)) confirms who you are, and authorization ([§74](./Section-74-Part10-Authorization-Modes-RBAC-ABAC-Node-Webhook.md)–[§75](./Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) confirms what you're allowed to do — but neither of those stages inspects the actual content of what you're trying to create. A request could be perfectly authenticated and authorized, and still be a Pod requesting privileged mode, a Deployment missing required labels, or an Ingress pointing at a namespace it shouldn't touch. Admission control is the final gate, after authorization, that inspects — and can even rewrite — the actual object content before it's ever persisted to etcd.

**Precise definition:** **Admission controllers** are the last stage of the API server request pipeline, running after authentication and authorization but before an object is persisted to etcd. Kubernetes distinguishes two categories: **built-in admission controllers** (compiled into the API server binary, enabled via `--enable-admission-plugins`, e.g. `NamespaceLifecycle`, `LimitRanger`, `ResourceQuota`) and **dynamic admission controllers** configured as **webhooks** — external HTTP services the API server calls out to for each matching request. Dynamic admission webhooks come in two kinds, both configured via their own API objects: **MutatingWebhookConfiguration**, whose webhooks run first and can modify (mutate) the object before it's finalized (injecting a sidecar container, setting a default label, adding a default resource limit), and **ValidatingWebhookConfiguration**, whose webhooks run second, after all mutations are complete, and can only accept or reject the object outright — never modify it. Both webhook types receive an **AdmissionReview** object describing the incoming request and respond with an allow/deny decision (and, for mutating webhooks, an optional JSON Patch describing the desired modification).

## 2. Why This Matters

- **Admission control is where organizational policy actually gets enforced as code**, beyond what RBAC's coarse verb/resource model can express — RBAC can grant "create pods," but only an admission webhook can enforce "every Pod must set `runAsNonRoot: true`" or "every Deployment must have a `team` label," making this section the natural convergence point of everything Part 10 has covered.
- **Mutating and Validating webhooks run in a strict, deliberate order (mutating first, validating second) precisely so validation always sees the final, fully-mutated object**, not an intermediate state — misunderstanding this ordering is a common source of confusing "why did my mutation not get validated correctly" debugging sessions.
- **Pod Security Admission ([§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md), the next section in this Part) is itself implemented as a built-in admission controller**, and the entire mechanism this section covers — the admission chain's position in the request lifecycle — is the direct prerequisite for understanding how Pod Security Standards actually get enforced.

🔑 **Key Takeaway:** Admission control is the final request-pipeline stage after authentication and authorization, split into built-in controllers and dynamic Mutating/Validating webhooks — mutating webhooks run first and can rewrite an object, validating webhooks run second on the final object and can only allow or reject it, making this the mechanism through which organizational policy beyond RBAC's reach actually gets enforced.

## 3. Prerequisites and Dependencies

Builds directly on [§76](./Section-76-Part10-ServiceAccounts-Tokens-Auto-Mounting-Bound-Tokens.md) (ServiceAccounts and tokens — webhook admission controllers themselves are frequently backed by in-cluster Pods that authenticate using exactly this mechanism), and back-references [§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md) (SecurityContext, Part 6, whose fields are commonly the specific target of policy enforced through validating webhooks) and [§41](../Part6/Section-41-Part6-ConfigMaps-Creation-Consumption.md)–[§42](../Part6/Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md) (ConfigMaps/Secrets, Part 6, since webhook TLS certificates and client configuration are typically stored using these same mechanisms).

## 4. Architecture: The Full Request Pipeline and the Two Webhook Types

```text
┌──────────────────────────────────────────────────────────────────────┐
│  1. Authentication (§73) — who is making this request?               │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. Authorization (§74–§75) — is this identity allowed to do this?   │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. ADMISSION CONTROL                                                │
│                                                                      │
│     a) Built-in admission controllers                                │
│        (NamespaceLifecycle, LimitRanger, ResourceQuota, ...)         │
│                          │                                           │
│                          ▼                                           │
│     b) MUTATING webhooks (MutatingWebhookConfiguration)              │
│        - run FIRST among dynamic webhooks                            │
│        - CAN modify the object (JSON Patch response)                 │
│        - e.g. inject a sidecar, set a default label                  │
│                          │                                           │
│                          ▼   (object is now in its FINAL form)       │
│     c) VALIDATING webhooks (ValidatingWebhookConfiguration)          │
│        - run SECOND, after all mutation is complete                  │
│        - CANNOT modify — only allow or reject                        │
│        - e.g. reject a Pod missing required SecurityContext fields   │
└──────────────────────────────┬───────────────────────────────────────┘
                               ▼ (only if every stage allows)
                     Object persisted to etcd
```

- **Mutating webhooks running before validating webhooks is the single most important ordering fact in this diagram** — it guarantees that whatever validation logic runs (whether built-in or a validating webhook) always evaluates the object's truly final state, including any sidecar injection or defaulting a mutating webhook performed.
- **Multiple webhooks of the same type can be registered simultaneously**, each targeting potentially different resource types or namespaces via label selectors on the `MutatingWebhookConfiguration`/`ValidatingWebhookConfiguration` object — the API server calls all matching webhooks of a given phase, and any single rejection at any point halts the request.
- **A webhook's `failurePolicy` (`Fail` or `Ignore`) determines what happens if the webhook endpoint itself is unreachable or times out** — `Fail` (the safer, generally recommended default) rejects the request outright if the webhook can't be reached, while `Ignore` allows the request through, which is a meaningful gap for security-enforcing webhooks specifically.

## 5. Hands-On: Admission Controller Mechanics

### 5.1 Inspecting Built-In Admission Controllers

**Purpose:** Show which built-in admission controllers are active on a cluster, and how they differ conceptually from dynamic webhooks.

**Syntax:**

```bash
kubectl exec -n kube-system kube-apiserver-<node> -- kube-apiserver --help | grep enable-admission-plugins
```

```yaml
# Excerpt of the kube-apiserver static Pod manifest
spec:
  containers:
    - command:
        - kube-apiserver
        - --enable-admission-plugins=NodeRestriction,ResourceQuota,LimitRanger,PodSecurity
```

**Example usage and expected output:**

```bash
$ kubectl create namespace no-quota-test
namespace/no-quota-test created

$ kubectl -n no-quota-test run test --image=nginx --requests='cpu=10000'
Error from server (Forbidden): pods "test" is forbidden: exceeded quota
```

**Production usage example:** `ResourceQuota` and `LimitRanger` are the built-in admission controllers that enforce resource governance ([§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md) and [§112](../Part14/Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md)) at the namespace boundary — they're always active by default on a properly configured cluster and require no external webhook infrastructure at all, unlike custom organizational policy.

**Common errors:** Assuming a rejected request due to a built-in admission controller (like a ResourceQuota violation) is an RBAC/authorization failure — the `Forbidden` wording is similar, but the actual cause and remediation (adjust the request/limit or the quota itself) are entirely different from an RBAC fix.

### 5.2 A Mutating Webhook That Injects a Default

**Purpose:** Show the shape of a mutating webhook's configuration and its JSON Patch-based modification mechanism.

**Syntax:**

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: MutatingWebhookConfiguration
metadata:
  name: default-labeler
webhooks:
  - name: labeler.platform.example.com
    clientConfig:
      service:
        name: labeler-webhook
        namespace: platform-system
        path: "/mutate"
      caBundle: <base64-encoded CA cert>
    rules:
      - apiGroups: ["apps"]
        apiVersions: ["v1"]
        operations: ["CREATE"]
        resources: ["deployments"]
    failurePolicy: Fail
    sideEffects: None
    admissionReviewVersions: ["v1"]
```

**Example usage and expected output:**

```bash
$ kubectl apply -f deployment-missing-labels.yaml
deployment.apps/web created

$ kubectl get deployment web -o jsonpath='{.metadata.labels}'
{"team":"unassigned","cost-center":"pending-review"}
# labels the mutating webhook injected, even though the submitted manifest had none
```

**Production usage example:** This exact pattern is how platform teams enforce organization-wide labeling standards (required for cost allocation, ownership tracking) without requiring every application team to remember to add them manually — the webhook fills in sensible defaults for anything missing, while still allowing explicit values submitted by the user to pass through unmodified.

**Common errors:** Setting `failurePolicy: Ignore` on a mutating webhook responsible for injecting security-relevant defaults (like a required SecurityContext field, [§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)) — if the webhook endpoint becomes unreachable, objects are silently admitted _without_ the intended mutation applied, defeating the webhook's entire purpose exactly when it's most needed.

### 5.3 A Validating Webhook That Enforces SecurityContext Policy

**Purpose:** Show a validating webhook rejecting a Pod that violates organizational security policy beyond what RBAC alone can express — directly building on the SecurityContext fields covered in Part 6.

**Syntax:**

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingWebhookConfiguration
metadata:
  name: securitycontext-enforcer
webhooks:
  - name: secctx.platform.example.com
    clientConfig:
      service:
        name: secctx-webhook
        namespace: platform-system
        path: "/validate"
      caBundle: <base64-encoded CA cert>
    rules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE"]
        resources: ["pods"]
    failurePolicy: Fail
    sideEffects: None
    admissionReviewVersions: ["v1"]
```

**Example usage and expected output:**

```bash
$ kubectl apply -f privileged-pod.yaml
Error from server: error when creating "privileged-pod.yaml":
admission webhook "secctx.platform.example.com" denied the request:
Pod spec.containers[0].securityContext.privileged must not be true
```

**Production usage example:** This is a hand-rolled equivalent of much of what Pod Security Admission's Restricted profile ([§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md), next section) enforces natively — many organizations start with a custom validating webhook like this before migrating to the built-in Pod Security Admission mechanism once it covers their specific policy needs, since it requires no custom webhook infrastructure to maintain.

**Common errors:** Writing validating webhook logic that inspects only the top-level Pod spec fields and misses equivalent settings nested under `initContainers` or `ephemeralContainers` — a genuinely common gap that lets a policy-violating configuration slip through via a container type the webhook's author didn't account for.

## 6. Production Usage Notes

- **Webhook admission controllers add latency to every matching request**, since the API server must synchronously call out to the webhook service and wait for a response before proceeding — a slow or overloaded webhook backend can measurably degrade `kubectl apply` responsiveness cluster-wide, making webhook performance and availability a genuine operational concern, not just a policy-design one.
- **`sideEffects: None` in a webhook's configuration is a declaration to the API server about whether the webhook has side effects outside the admission request itself** (important for correct behavior during dry-run requests) — webhooks with genuine side effects must handle `dry-run` requests specially to avoid taking real action during a `kubectl apply --dry-run=server`.
- **Tools like OPA Gatekeeper and Kyverno provide a policy-as-code layer built entirely on top of this ValidatingWebhookConfiguration/MutatingWebhookConfiguration mechanism**, letting organizations write policy in a higher-level language (Rego for Gatekeeper, YAML-based rules for Kyverno) rather than hand-rolling a custom webhook service from scratch.

## 7. Security Considerations

- **`failurePolicy: Fail` should be the default for any admission webhook enforcing genuine security policy** — `Ignore` silently allows requests through unmodified/unvalidated whenever the webhook is unreachable, which is precisely the failure mode an attacker (or an unrelated outage) could exploit or benefit from.
- **Webhook services themselves are a meaningful part of the cluster's trusted computing base** — since they can approve or reject (and, for mutating webhooks, rewrite) essentially any object in the cluster, the Pods running webhook backends deserve the same or greater SecurityContext hardening ([§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)) and RBAC scrutiny as any other privileged, cluster-wide component.
- **Namespace label selectors on webhook configurations are the standard way to exclude the `kube-system` namespace and the webhook's own namespace from its own rules** — omitting this is a classic cause of a cluster-bricking deadlock, where the webhook required to admit its own replacement Pod is itself down, and nothing can be created (including the fix) until manual intervention bypasses the webhook.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                                     | Resolution Path                                                                                                                                                        |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Every `kubectl apply` in the cluster starts failing or timing out          | A `failurePolicy: Fail` webhook's backend is unreachable, and its rules match too broadly (e.g., all namespaces) | Check webhook endpoint health; ensure `kube-system` and the webhook's own namespace are excluded via selectors                                                         |
| An object is admitted without an expected mutation applied                 | Mutating webhook has `failurePolicy: Ignore` and its backend was unreachable at request time                     | Investigate webhook backend availability; consider `Fail` for policy-critical mutations                                                                                |
| A validating webhook rejects an object that looks compliant                | Mutating webhooks ran first and altered the object in a way the validating webhook then flags                    | Inspect the object's final, post-mutation state (`kubectl get -o yaml`), not the originally submitted manifest                                                         |
| Cluster is deadlocked — can't create any Pods, including the webhook's own | Webhook's rules unintentionally match its own namespace, and it's currently down, blocking its own restart       | Use `kubectl label namespace <ns> policy-exempt=true` matched by the webhook's `namespaceSelector` as an escape hatch, or delete the webhook configuration temporarily |

## 9. Best Practices

- Exclude `kube-system` and the webhook's own namespace from a webhook's `namespaceSelector`/`objectSelector` rules to avoid cluster-bricking deadlocks.
- Prefer `failurePolicy: Fail` for policy-enforcing webhooks, and invest in webhook backend availability (replicas, health checks, PodDisruptionBudgets) to keep that strict failure mode from causing unnecessary outages.
- Adopt an established policy engine (OPA Gatekeeper, Kyverno) rather than hand-rolling custom webhook services for anything beyond a narrow, simple use case.

## 10. Common Anti-Patterns / Mistakes

- **Setting `failurePolicy: Ignore` on a webhook that enforces genuine security policy**, silently defeating the policy exactly when the webhook backend is unavailable.
- **Forgetting to exclude the webhook's own namespace from its own rules**, creating a self-referential deadlock the moment the webhook backend needs to restart.
- **Writing validating webhook logic that only checks the top-level container spec**, missing equivalent policy violations in `initContainers` or `ephemeralContainers`.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a mutating and a validating admission webhook?"_
**Model answer:** A mutating webhook runs first and can actually change the object being submitted — injecting a default label, adding a sidecar container, setting a missing field — by returning a JSON Patch in its response. A validating webhook runs afterward, once all mutations are complete, and can only accept or reject the object outright; it has no ability to modify it. This ordering guarantees validation always evaluates the object's true final state, not an intermediate one.
_What the interviewer is probing for:_ Basic grasp of the two webhook types and, critically, their strict ordering relationship.

**🎯 Intermediate:** _"A team says an object was rejected by a validating webhook for a field they never set. What's the likely explanation?"_
**Model answer:** Because mutating webhooks run before validating webhooks and operate on the object's final, post-mutation state, the field the validating webhook flagged may well have been added or changed by a mutating webhook, not by the user's original submission. I'd check `kubectl get <resource> -o yaml` after the fact if the object was ultimately created, or more usefully, review the mutating webhook's logic and any registered `MutatingWebhookConfiguration` matching that resource type, since the validating rejection is operating on the object as mutated, which may differ meaningfully from what was originally submitted.
_What the interviewer is probing for:_ Applying the mutating-before-validating ordering fact to a real debugging scenario rather than reciting it abstractly.

**🎯 Senior:** _"Why is `failurePolicy: Fail` generally recommended for security-enforcing webhooks, and what operational burden does that recommendation create?"_
**Model answer:** `Fail` ensures that if the webhook backend is unreachable, requests are rejected rather than silently admitted without the intended validation or mutation — for a webhook enforcing genuine security policy, `Ignore` would mean an outage of the webhook itself becomes a security bypass, which is precisely the wrong failure mode for anything security-critical. The operational cost is that the webhook backend's own availability now directly gates the availability of the entire API server for any matching request — a webhook backend outage with `Fail` set can effectively halt `kubectl apply` operations cluster-wide for matching resources. This means adopting `Fail` for a security-critical webhook comes with a real obligation to invest in that webhook's own reliability (multiple replicas, a PodDisruptionBudget, proper health checks, and careful namespace exclusions to avoid self-deadlock), not just flipping the setting and moving on.
_What the interviewer is probing for:_ Understanding that `failurePolicy: Fail` is the security-correct default but shifts genuine availability risk onto the webhook backend, requiring a deliberate reliability investment to pair with it.

**🎯 Architect:** _"Design the admission control strategy for a large organization that needs to enforce SecurityContext standards, mandatory labeling, and image provenance checks across all clusters."_
**Model answer:** Rather than hand-rolling three separate custom webhook services, I'd adopt an established policy engine — OPA Gatekeeper or Kyverno — as the single dynamic admission mechanism, expressing all three policy domains (SecurityContext enforcement building on [§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)'s baseline, mandatory labeling, and image provenance/signature verification tying into supply-chain security material from Part 15) as declarative policy objects within that engine rather than as bespoke webhook code, which is both more auditable and easier for a platform team to maintain long-term. I'd set `failurePolicy: Fail` for the security- and provenance-related policies given their criticality, paired with a highly available policy engine deployment (multiple replicas across nodes, a PodDisruptionBudget, and careful `namespaceSelector` exclusions for `kube-system` and the policy engine's own namespace to avoid self-deadlock). I'd roll out new policies in a dry-run/audit mode first — most modern policy engines support this — observing violations across real traffic for a period before flipping to actual enforcement, to catch unintended breakage before it becomes an outage. Finally, I'd version-control every policy definition in the same GitOps repository ([§88](../Part11/Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md)) driving the rest of cluster configuration, so policy changes go through the same review process as any other infrastructure change, and I'd feed policy violation events into the cluster's observability stack ([§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md)–[§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)) so drift and attempted violations are visible over time, not just blocked silently at the moment they occur.
_What the interviewer is probing for:_ Ability to design admission control as a coherent, maintainable, observable platform capability using established tooling, rather than a collection of bespoke, individually-maintained webhook services — plus awareness of rollout safety (dry-run/audit mode) for policy changes with cluster-wide blast radius.

## 12. Common Misconceptions

1. **"Validating webhooks can modify the object being validated, just like mutating webhooks."** They cannot — a validating webhook may only allow or reject a request; only mutating webhooks, which run first, can modify the object via a JSON Patch.
2. **"Admission control happens before authorization."** It happens after both authentication and authorization — an object must already be from an authenticated, authorized request before admission controllers ever see it.
3. **"`failurePolicy: Ignore` is a safe, conservative default."** For any policy-enforcing webhook, it's actually the riskier choice — it silently allows requests through unmodified/unvalidated whenever the webhook backend is unreachable, precisely defeating the policy at the moment it's most needed.
4. **"A rejected request from a built-in admission controller (like ResourceQuota) is the same kind of failure as an RBAC denial."** Both can produce similarly worded `Forbidden`-style errors, but they occur at different stages of the request pipeline and require entirely different remediation.

## 13. 🔑 Key Takeaways

- Admission control is the final request-pipeline stage, after authentication ([§73](./Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md)) and authorization ([§74](./Section-74-Part10-Authorization-Modes-RBAC-ABAC-Node-Webhook.md)–[§75](./Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)), and includes both built-in controllers and dynamic Mutating/Validating webhooks.
- Mutating webhooks run first and can rewrite an object via JSON Patch; validating webhooks run second, on the final mutated object, and can only allow or reject it — never modify it.
- `failurePolicy: Fail` is the security-correct default for policy-enforcing webhooks, but it shifts real availability risk onto the webhook backend, requiring a genuine reliability investment.
- Excluding `kube-system` and the webhook's own namespace from its rules is essential to avoid a self-referential cluster deadlock.
- Established policy engines (OPA Gatekeeper, Kyverno) built on this exact webhook mechanism are generally preferable to hand-rolled custom webhook services for real organizational policy enforcement.

## 14. Related Concepts & What's Next

This section built on [§76](./Section-76-Part10-ServiceAccounts-Tokens-Auto-Mounting-Bound-Tokens.md)'s ServiceAccount and token mechanics (which webhook backend Pods themselves rely on to authenticate), and back-referenced [§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md) (SecurityContext, Part 6) and [§41](../Part6/Section-41-Part6-ConfigMaps-Creation-Consumption.md)–[§42](../Part6/Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md) (ConfigMaps/Secrets, Part 6) as the concrete policy targets and credential-storage mechanisms this admission layer commonly interacts with. This closes out the authentication-through-admission arc of Part 10's core security pipeline. [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md), next, covers Pod Security Standards and Pod Security Admission — a built-in admission controller, using exactly the mechanism covered in this section, that enforces the Privileged/Baseline/Restricted policy tiers natively without requiring a custom webhook at all.

**Next Section:** [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md) — `Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md`
