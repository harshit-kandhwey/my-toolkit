# Section 76 (Part 10): ServiceAccounts: Tokens, Auto-Mounting, and Bound Service Account Tokens

## 1. Definition

**Plain language:** Every Pod that needs to talk to the Kubernetes API — a controller reconciling state, a CI job deploying a new version, a sidecar checking its own Pod's status — needs an identity to authenticate with. ServiceAccounts are that identity for in-cluster workloads, and how their credentials get created, mounted, and eventually expire has changed significantly across Kubernetes versions, in ways that matter a great deal for security posture.

**Precise definition:** A **ServiceAccount** is a namespaced API object representing the identity of processes running inside Pods. Every namespace has a `default` ServiceAccount automatically, and every Pod is assigned one — either explicitly via `spec.serviceAccountName` or implicitly via `default` — whose credentials the kubelet automatically projects into the Pod's filesystem at `/var/run/secrets/kubernetes.io/serviceaccount/`. Historically (pre-1.24), Kubernetes auto-created a long-lived, non-expiring **Secret-backed token** for every ServiceAccount, mounted into every Pod using that ServiceAccount by default. Modern Kubernetes (1.24+) instead uses **Bound Service Account Tokens** — short-lived, audience-bound, automatically rotated JWTs generated via the **TokenRequest API** and delivered through a **projected volume**, which are cryptographically bound to the specific Pod (and optionally a specific audience, like a particular external service) that requested them, rather than existing as a standalone, indefinitely valid Secret object. `automountServiceAccountToken: false` (settable at the ServiceAccount or Pod level) disables this automatic credential mounting entirely for workloads that never call the API server.

## 2. Why This Matters

- **The shift from long-lived Secret-backed tokens to short-lived Bound Service Account Tokens is one of the most consequential security improvements in recent Kubernetes history**, directly reducing the value of a leaked token (it expires quickly and is bound to a specific Pod/audience) compared to the old model where a leaked token remained valid indefinitely.
- **Every Pod gets a mounted ServiceAccount token by default, whether it needs one or not** — this is a very common, very avoidable source of unnecessary attack surface, since most application workloads never actually call the Kubernetes API and gain nothing from having a live credential sitting in their filesystem.
- **CKS explicitly tests the ability to disable unnecessary auto-mounting and reason about token lifetime as a hardening measure**, making this section's material directly exam-relevant at the CKS level, in addition to being foundational CKA/CKAD content.

🔑 **Key Takeaway:** Modern Kubernetes ServiceAccounts authenticate via short-lived, audience-bound Bound Service Account Tokens delivered through a projected volume rather than a long-lived Secret, and disabling `automountServiceAccountToken` for any workload that doesn't call the API server is a simple, high-value, frequently overlooked hardening step.

## 3. Prerequisites and Dependencies

Builds directly on [§75](./Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md) (RBAC — the permission grants that ServiceAccount identities are bound to via RoleBindings/ClusterRoleBindings) and [§73](./Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md) (Authentication, where ServiceAccounts were first introduced as a distinct identity category from Users).

## 4. Architecture: Token Evolution — Legacy Secret-Backed vs. Bound Tokens

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LEGACY MODEL (pre-1.24 default)                          │
│                                                                             │
│  ServiceAccount ──auto-creates──► Secret (type:                             │
│                                    kubernetes.io/service-account-token)     │
│                                    - NEVER expires by default               │
│                                    - Same value mounted into EVERY Pod      │
│                                      using this ServiceAccount              │
│                                    - Leaked token = valid indefinitely      │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                MODERN MODEL (1.24+, Bound Service Account Tokens)           │
│                                                                             │
│  Pod created ──kubelet calls──► TokenRequest API                            │
│                                    │                                        │
│                                    ▼                                        │
│                    Short-lived JWT issued:                                  │
│                    - bound to THIS Pod specifically (UID-bound)             │
│                    - default expiry: 1 hour                                 │
│                    - optionally audience-bound (aud claim)                  │
│                    - delivered via PROJECTED VOLUME, not a Secret object    │
│                                    │                                        │
│                                    ▼                                        │
│                    kubelet automatically ROTATES the token                  │
│                    before expiry, transparently to the app                  │
└─────────────────────────────────────────────────────────────────────────────┘

              automountServiceAccountToken: false
                              │
                              ▼
              No token projected at all — for workloads
              that never call the Kubernetes API
```

- **The projected volume mechanism is what makes rotation transparent** — instead of a static file written once at Pod start, the kubelet periodically refreshes the token file in place, and any client library that re-reads the file before each API call transparently picks up the renewed token.
- **A Bound Service Account Token being tied to a specific Pod UID** means it becomes invalid the moment that specific Pod is deleted, unlike the legacy Secret-backed token, which remained valid for as long as the ServiceAccount itself existed, entirely independent of any particular Pod's lifecycle.
- **`automountServiceAccountToken: false` can be set at either the ServiceAccount or the individual Pod level**, with the Pod-level setting taking precedence — mirroring the same override relationship SecurityContext uses between Pod and container level.

## 5. Hands-On: Working with ServiceAccount Tokens

### 5.1 Inspecting the Modern, Auto-Mounted Bound Token

**Purpose:** Show exactly what a Pod's default, auto-mounted token looks like in a modern cluster, and confirm it's a short-lived JWT rather than a static Secret value.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-caller
spec:
  serviceAccountName: default
  containers:
    - name: app
      image: myregistry.example.com/api-client:1.0
```

**Example usage and expected output:**

```bash
$ kubectl apply -f api-caller.yaml
pod/api-caller created

$ kubectl exec api-caller -- cat /var/run/secrets/kubernetes.io/serviceaccount/token | cut -d'.' -f2 | base64 -d
{"aud":["https://kubernetes.default.svc"],"exp":1735689600,"iat":1735686000,
 "sub":"system:serviceaccount:default:default", ...}

$ kubectl exec api-caller -- ls -la /var/run/secrets/kubernetes.io/serviceaccount/
# token, ca.crt, namespace — delivered via a projected volume, not a Secret volume
```

**Production usage example:** The `exp` (expiry, roughly one hour from `iat`) and `aud` (audience) claims visible in the decoded JWT are exactly why a leaked Bound Service Account Token is far less dangerous than a leaked legacy token — the window of usability is short, and the kubelet transparently rotates it well before expiry for any Pod that's still running.

**Common errors:** Assuming the token file's content is static for the Pod's entire lifetime — client libraries or scripts that read the token file once at startup and cache it in memory will find their cached credential expires within the hour, while libraries that re-read the file per-request handle rotation transparently.

### 5.2 Disabling Auto-Mounting for Workloads That Don't Call the API

**Purpose:** Demonstrate the simple, high-value hardening step of removing an unnecessary credential from workloads that never need to call the Kubernetes API.

**Syntax:**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: frontend-sa
  namespace: production
automountServiceAccountToken: false # applies to every Pod using this SA by default
---
apiVersion: v1
kind: Pod
metadata:
  name: frontend
  namespace: production
spec:
  serviceAccountName: frontend-sa
  containers:
    - name: nginx
      image: nginx:1.25
```

**Example usage and expected output:**

```bash
$ kubectl apply -f frontend.yaml
serviceaccount/frontend-sa created
pod/frontend created

$ kubectl exec frontend -- ls /var/run/secrets/kubernetes.io/serviceaccount/
ls: /var/run/secrets/kubernetes.io/serviceaccount/: No such file or directory
```

**Production usage example:** A static web-serving frontend, a batch job that only reads from an external database, or any workload whose entire function is unrelated to the Kubernetes API itself should have this set — removing the token entirely means there's simply nothing for an attacker to steal from that Pod even if it's fully compromised via a code-level vulnerability.

**Common errors:** Setting `automountServiceAccountToken: false` on a ServiceAccount whose Pods actually do need to call the API occasionally (a sidecar performing a health-check-driven API call, for instance) — this produces confusing runtime authentication failures that look unrelated to the actual root cause until someone checks this specific field.

### 5.3 Requesting an Audience-Bound Token via the TokenRequest API Directly

**Purpose:** Show how a workload can request a token scoped to a specific external audience (not the Kubernetes API itself), a pattern common in workload-identity-federation setups.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: external-service-caller
spec:
  serviceAccountName: external-caller-sa
  containers:
    - name: app
      image: myregistry.example.com/app:1.0
      volumeMounts:
        - name: vault-token
          mountPath: /var/run/secrets/tokens
  volumes:
    - name: vault-token
      projected:
        sources:
          - serviceAccountToken:
              path: vault-token
              expirationSeconds: 600 # short-lived, 10-minute token
              audience: vault # bound to THIS audience only, not the API server
```

**Example usage and expected output:**

```bash
$ kubectl apply -f external-caller.yaml
pod/external-service-caller created

$ kubectl exec external-service-caller -- cat /var/run/secrets/tokens/vault-token | cut -d'.' -f2 | base64 -d
{"aud":["vault"],"exp":..., "sub":"system:serviceaccount:production:external-caller-sa"}
```

**Production usage example:** This exact pattern underlies HashiCorp Vault's Kubernetes authentication method and the External Secrets Operator ([§80](./Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md)) — the external service verifies the token's signature against the cluster's public key and its `aud` claim matches its own identity, establishing trust without Vault ever needing a separate, independently managed credential for that Pod.

**Common errors:** Setting `audience` to `https://kubernetes.default.svc` (or omitting it) when the intent was actually to scope the token to an external service — an audience mismatch causes the external verifier to reject the token outright, since audience-bound tokens are deliberately unusable against any endpoint whose identity doesn't match the `aud` claim.

## 6. Production Usage Notes

- **The migration from legacy Secret-backed tokens to Bound Service Account Tokens happened gradually across Kubernetes 1.22–1.24**, and clusters upgraded through that window may still have legacy long-lived token Secrets lingering from ServiceAccounts created before the change — an audit of `kubectl get secrets --all-namespaces --field-selector type=kubernetes.io/service-account-token` is worthwhile on any older cluster.
- **The default token expiry (roughly one hour, configurable via `--service-account-max-token-expiration` cluster-wide) balances security against unnecessary rotation overhead** — very short expirations increase the frequency of TokenRequest API calls the kubelet must make, which matters at very large cluster scale.
- **Client libraries in every major language (client-go, kubernetes-client/python, etc.) handle Bound Token rotation transparently** as of reasonably recent versions — this is rarely something application code needs to implement manually, but older or hand-rolled HTTP clients that cache the token at startup are a real gap to watch for.

## 7. Security Considerations

- **Disabling `automountServiceAccountToken` for any workload that doesn't call the Kubernetes API is one of the simplest, highest-value hardening steps available** — it eliminates a credential that provides zero functional benefit to that workload while remaining a genuine target if the container is compromised.
- **A leaked Bound Service Account Token is still a real credential for its remaining lifetime** — short expiry reduces but does not eliminate the risk window, and a sufficiently fast automated attack could still exploit a freshly leaked token within its validity period.
- **Audience-bound tokens (via the `serviceAccountToken` projected volume source) should always specify a narrow, specific `audience`** — a token with no audience restriction (or one bound to the Kubernetes API server itself) being handed to an external service is a meaningful over-scoping mistake, since that same token could then also be replayed against the Kubernetes API itself.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                                         | Resolution Path                                                                                        |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| A workload's API calls start failing after roughly an hour of running | Client library cached the token at startup instead of re-reading it, and the token has since rotated | Use a client library version that re-reads the projected token file per request, or fetches it fresh   |
| `/var/run/secrets/kubernetes.io/serviceaccount/` is missing entirely  | `automountServiceAccountToken: false` set at the ServiceAccount or Pod level                         | Confirm whether the workload actually needs API access; if so, remove or override the `false` setting  |
| An external service (e.g., Vault) rejects a Pod's projected token     | Token's `audience` claim doesn't match what the external verifier expects                            | Set `audience` explicitly in the `serviceAccountToken` projected volume source to match the consumer   |
| Legacy long-lived token Secret still exists for a ServiceAccount      | ServiceAccount was created before the cluster's upgrade to Bound Token defaults (pre-1.24 legacy)    | Audit and rotate/delete legacy `kubernetes.io/service-account-token` Secrets no longer actively needed |

## 9. Best Practices

- Set `automountServiceAccountToken: false` by default for every ServiceAccount, and enable it explicitly only for workloads with a demonstrated need to call the Kubernetes API.
- Use audience-scoped, short-expiry projected tokens for any integration with an external service (Vault, a cloud provider's workload identity federation), rather than relying on the default Kubernetes-API-audience token.
- Periodically audit for lingering legacy Secret-backed ServiceAccount tokens on clusters that have been upgraded across the 1.24 boundary, since these don't automatically disappear on upgrade.

## 10. Common Anti-Patterns / Mistakes

- **Leaving `automountServiceAccountToken` at its default (enabled) for every workload**, including ones that never call the Kubernetes API, needlessly leaving a live credential in every such Pod's filesystem.
- **Caching a ServiceAccount token in application memory at startup** without accounting for its short expiry and the kubelet's transparent rotation, causing avoidable authentication failures after roughly an hour.
- **Handing an unscoped (default-audience) token to an external, non-Kubernetes service** rather than requesting a properly audience-bound token specific to that integration.

## 11. Interview Questions

**🎯 Beginner:** _"What happens to a Pod's ServiceAccount token if you don't explicitly set `serviceAccountName`?"_
**Model answer:** The Pod is automatically assigned the `default` ServiceAccount of its namespace, and — unless `automountServiceAccountToken: false` is set somewhere in the chain — the kubelet automatically mounts a token for that ServiceAccount into the Pod's filesystem at `/var/run/secrets/kubernetes.io/serviceaccount/`, giving the Pod a working, if unintentional, identity for calling the Kubernetes API.
_What the interviewer is probing for:_ Awareness that every Pod gets an identity by default, whether or not that was a deliberate decision.

**🎯 Intermediate:** _"What's the practical security difference between the legacy Secret-backed ServiceAccount token model and Bound Service Account Tokens?"_
**Model answer:** Legacy tokens were static, non-expiring JWTs stored as a standalone Secret object, shared identically across every Pod using that ServiceAccount, meaning a leaked token remained valid indefinitely and independent of any specific Pod's lifecycle. Bound Service Account Tokens, by contrast, are short-lived (roughly one hour by default), cryptographically bound to the specific requesting Pod's UID, and delivered via a projected volume that the kubelet transparently rotates before expiry — so a leaked Bound Token has a narrow usability window and becomes invalid entirely once its specific Pod is deleted, substantially reducing the value of a leaked credential to an attacker.
_What the interviewer is probing for:_ Understanding of the concrete security improvement, not just that "tokens changed" at some version.

**🎯 Senior:** _"A team asks why their application's Kubernetes API calls fail intermittently after their Pods have been running for a while, despite nothing in their deployment changing. What would you check?"_
**Model answer:** My first hypothesis would be token expiry interacting with how the client reads its credential — if the application (or an older client library, or a hand-rolled HTTP client) reads the ServiceAccount token file once at process startup and caches it in memory rather than re-reading the projected volume before each API call, it will hold onto an increasingly stale token that eventually crosses its `exp` claim and gets rejected by the API server, roughly on the default one-hour boundary. I'd verify this by decoding the token's JWT claims to confirm the expiry window, checking the client library version and its token-handling behavior, and confirming the failures correlate in time with roughly that expiry window rather than, say, a deployment or restart event. The fix is almost always upgrading to a client library version that properly re-reads the projected token file, rather than anything related to RBAC or authorization, which a team unfamiliar with Bound Token rotation might otherwise incorrectly suspect first.
_What the interviewer is probing for:_ Recognizing token rotation as a distinct failure mode from RBAC/authorization issues, and a methodical approach to correlating the failure pattern with token lifetime.

**🎯 Architect:** _"Design the ServiceAccount and token strategy for a platform where workloads need to authenticate to both the Kubernetes API and several external systems (a secrets manager, a cloud provider API)."_
**Model answer:** I'd start from a default-deny posture: every ServiceAccount ships with `automountServiceAccountToken: false`, and teams must explicitly opt a workload into API access only when there's a demonstrated need, keeping the vast majority of Pods with no live Kubernetes API credential in their filesystem at all. For workloads that do need Kubernetes API access, I'd rely on the default Bound Service Account Token mechanism rather than any legacy pattern, trusting the kubelet's transparent rotation. For integration with external systems — a secrets manager like Vault, or cloud-provider workload identity federation for AWS/GCP APIs — I'd use explicit projected-volume `serviceAccountToken` sources with a narrow, correctly scoped `audience` per integration and a short `expirationSeconds`, rather than reusing the default Kubernetes-API-audience token against an external verifier, since that would allow an unintended, broader replay surface. I'd wire RBAC ([§75](./Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) bindings to these ServiceAccounts following the same least-privilege principle covered there, and I'd periodically audit both for lingering legacy Secret-backed tokens and for any ServiceAccount with `automountServiceAccountToken` left enabled without a documented justification, treating both as drift from the intended baseline that CI-driven manifest linting ([§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)) should catch automatically.
_What the interviewer is probing for:_ Ability to design a coherent, defense-in-depth token strategy spanning both in-cluster and external authentication needs, with default-deny as the starting posture rather than default-allow.

## 12. Common Misconceptions

1. **"Every Pod automatically gets a ServiceAccount token only if I explicitly ask for one."** The opposite is true — every Pod gets one mounted by default (via the `default` ServiceAccount, if nothing else) unless `automountServiceAccountToken: false` is explicitly set somewhere in the chain.
2. **"ServiceAccount tokens are static, long-lived credentials in every modern cluster."** As of Kubernetes 1.24+, the default is short-lived, automatically rotated Bound Service Account Tokens, not the legacy Secret-backed model.
3. **"Disabling `automountServiceAccountToken` breaks anything that might need it later."** It's safely reversible per-workload and should be the default-off posture, enabled explicitly and narrowly only where a genuine API-calling need exists.
4. **"A ServiceAccount token is only useful for talking to the Kubernetes API."** The TokenRequest API and projected volumes support audience-bound tokens scoped to entirely external services, a pattern widely used for workload identity federation with tools like Vault.

## 13. 🔑 Key Takeaways

- ServiceAccounts represent workload identity, with every Pod assigned one (explicitly or via the namespace's `default`) and a token auto-mounted by default unless explicitly disabled.
- Modern Kubernetes uses short-lived, Pod-bound, automatically rotated Bound Service Account Tokens delivered via a projected volume, a substantial security improvement over the legacy non-expiring Secret-backed model.
- `automountServiceAccountToken: false` is a simple, high-value, frequently overlooked hardening step for any workload that never calls the Kubernetes API.
- Audience-bound projected tokens (via `serviceAccountToken.audience`) let workloads authenticate to external systems like Vault without a separately managed credential, and should always specify a narrow, correct audience.
- Client libraries must re-read the projected token file rather than caching it at startup, since Bound Tokens expire and rotate on a roughly one-hour default cycle.

## 14. Related Concepts & What's Next

This section builds directly on [§75](./Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)'s RBAC mechanics, which determine what a ServiceAccount's resolved identity is actually permitted to do once authenticated with one of these tokens. [§77](./Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md), next, moves to the request lifecycle stage immediately after authorization: admission controllers, and specifically the validating and mutating webhooks that can inspect, modify, or reject a request even after RBAC has already approved it.

**Next Section:** [§77](./Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md) — `Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md`
