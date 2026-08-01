# Section 73 (Part 10): Authentication in Kubernetes: Users, ServiceAccounts, X.509 Certs, OIDC

## 1. Definition

**Plain language:** Before Kubernetes decides _what_ a request is allowed to do, it first has to figure out _who_ is making the request at all. Authentication is that identity check — and Kubernetes is unusual in that it has no built-in user database, no `kubectl create user` command, and no login form. Every request arriving at the API server must prove its identity through one of a small set of pluggable mechanisms, and the API server itself never stores a list of human users anywhere.

**Precise definition:** **Authentication** in Kubernetes is the process by which the **kube-apiserver** establishes the identity of a request's caller before any authorization check occurs. Every authenticated request resolves to a **username** and a set of **group** memberships, which are then handed to the authorization layer (§74). Kubernetes distinguishes two broad identity categories: **Users** (humans or external systems, never represented as a first-class API object — Kubernetes has no `User` resource) and **ServiceAccounts** (`serviceaccounts` API objects, representing the identity of a Pod or in-cluster process, namespaced and fully managed by the cluster). The API server supports multiple concurrent **authentication modules** — X.509 client certificates, static token/password files (deprecated), bearer tokens (including ServiceAccount tokens), and **webhook** or **OIDC** (OpenID Connect) authentication for delegating identity verification to an external identity provider — and tries each configured module in turn until one succeeds or all fail, at which point the request is rejected with `401 Unauthorized`.

## 2. Why This Matters

- **Kubernetes deliberately has no built-in user management system** — this single fact drives nearly every real-world Kubernetes identity architecture decision, because "how do I add a user" has no `kubectl` answer; it always routes through an external mechanism (a certificate signed by the cluster CA, or federation to an existing identity provider via OIDC).
- **ServiceAccounts, unlike Users, are genuine API objects that Pods authenticate as automatically** — this is the identity mechanism a Pod uses to talk to the API server (for example, a controller watching resources), and it is foundational to how RBAC (§75) is actually applied to workloads rather than only to humans.
- **OIDC integration is the production-standard answer for human authentication at any real organization**, because it lets a cluster delegate identity to an existing corporate identity provider (Okta, Azure AD, Google Workspace) rather than distributing long-lived client certificates to every engineer — a pattern that scales identity lifecycle management (onboarding, offboarding, MFA) far better than certificates ever could.

🔑 **Key Takeaway:** Kubernetes authenticates requests through pluggable modules (X.509 certs, bearer tokens, OIDC, webhooks) that each resolve to a username and group set — but Kubernetes itself has no user store; Users are always external, while ServiceAccounts are genuine, cluster-managed API objects representing in-cluster workload identity.

## 3. Prerequisites and Dependencies

Builds on §41–§42 (Part 6, ConfigMaps and Secrets — the storage mechanisms often underlying kubeconfig credentials, OIDC client secrets, and token material) and assumes familiarity with the Pod spec anatomy (§24) where a Pod's `serviceAccountName` field first appears. This section is the entry point to Part 10's full security and RBAC arc.

## 4. Architecture: The Authentication Chain

```text
┌──────────────────────────────────────────────────────────────────────┐
│                     Incoming request to kube-apiserver               │
│         (kubectl, a Pod's mounted token, a CI/CD pipeline, etc.)     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
      ┌─────────────────────────────────────────────────────────┐
      │  Authentication chain — modules tried IN ORDER,         │
      │  first success wins, ALL must fail to reject            │
      │                                                         │
      │  1. X.509 Client Certificate  (CN = username,           |
      │     O = group membership)                               │
      │  2. Bearer Token                                        │
      │     - Static token file (deprecated)                    │
      │     - ServiceAccount token (JWT, signed by cluster)     │
      │     - Bootstrap token (node-join only, §16)             │
      │  3. OIDC (ID token from external Identity Provider)     │
      │  4. Webhook (delegates to external authn service)       │
      └──────────────────────────┬──────────────────────────────┘
                                 │ success → identity established
                                 ▼
                  username: "jane@example.com"
                  groups: ["engineering", "system:authenticated"]
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │   Authorization (§74) — RBAC, │
                  │   ABAC, Node, Webhook modes   │
                  └───────────────────────────────┘
                                  │
                                  ▼
                      Admission Controllers (§77)
```

- **Every configured authentication module runs in sequence for every request** — the API server does not know in advance which mechanism a given client will use, so it tries each in a fixed order until one succeeds.
- **Failure of one module is not rejection** — only if _every_ configured module fails to authenticate the request does the API server return `401 Unauthorized`; this is why a cluster can support both human OIDC logins and Pod ServiceAccount tokens simultaneously without conflict.
- **The output of authentication is always just a username and group list** — Kubernetes has no concept of "roles" or "permissions" at this stage; that mapping happens entirely in the authorization layer (§74) that follows.

## 5. Hands-On: Authentication Mechanisms in Practice

### 5.1 X.509 Client Certificate Authentication

**Purpose:** Show how a human user's identity is established via a client certificate signed by the cluster's Certificate Authority, the default mechanism `kubeadm`-bootstrapped clusters use for the initial `admin` user.

**Syntax:**

```bash
# Generate a private key and CSR for a new user "jane"
openssl genrsa -out jane.key 2048
openssl req -new -key jane.key -out jane.csr -subj "/CN=jane/O=engineering"

# Submit as a Kubernetes CertificateSigningRequest
kubectl apply -f - <<EOF
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata:
  name: jane-csr
spec:
  request: $(cat jane.csr | base64 | tr -d '\n')
  signerName: kubernetes.io/kube-apiserver-client
  usages: ["client auth"]
EOF

kubectl certificate approve jane-csr
kubectl get csr jane-csr -o jsonpath='{.status.certificate}' | base64 -d > jane.crt
```

**Example usage and expected output:**

```bash
$ kubectl --client-certificate=jane.crt --client-key=jane.key \
    --server=https://k8s-api.example.com:6443 get pods
Error from server (Forbidden): pods is forbidden: User "jane" cannot list resource "pods"
```

**Production usage example:** The `Forbidden` response above is the expected, correct behavior — the certificate proves _who jane is_ (authentication succeeded), but no RoleBinding (§75) grants her permission yet; this is the canonical demonstration that authentication and authorization are strictly separate stages.

**Common errors:** The `CN` (Common Name) field in the certificate subject becomes the Kubernetes **username** and the `O` (Organization) field becomes **group** membership — mixing these up (or forgetting `O` entirely) is a frequent source of RBAC bindings silently not matching the expected user or group.

### 5.2 ServiceAccounts and Their Auto-Mounted Tokens

**Purpose:** Show how a Pod authenticates to the API server using its ServiceAccount's automatically mounted token, without any human involvement.

**Syntax:**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ci-deployer
  namespace: production
---
apiVersion: v1
kind: Pod
metadata:
  name: deployer-pod
  namespace: production
spec:
  serviceAccountName: ci-deployer
  containers:
    - name: app
      image: myregistry.example.com/deployer:1.0
```

**Example usage and expected output:**

```bash
$ kubectl apply -f serviceaccount.yaml
serviceaccount/ci-deployer created
pod/deployer-pod created

$ kubectl exec deployer-pod -- ls /var/run/secrets/kubernetes.io/serviceaccount/
ca.crt  namespace  token

$ kubectl exec deployer-pod -- cat /var/run/secrets/kubernetes.io/serviceaccount/token
eyJhbGciOiJSUzI1NiIsImtpZCI6...   # a signed, time-bound JWT
```

**Production usage example:** Every in-cluster controller, operator, or CI/CD job that calls the Kubernetes API — ArgoCD reconciling a GitOps repo, a custom operator watching a CRD — authenticates using exactly this pattern: a ServiceAccount's projected token, never a human's personal credential, which keeps workload identity auditable and independently revocable (full token-lifecycle depth in §76).

**Common errors:** Assuming a Pod with no `serviceAccountName` specified has no identity at all — every Pod is automatically assigned the `default` ServiceAccount of its namespace unless one is explicitly set, which is itself a common over-permissioning trap if `default` has been granted more RBAC access than intended.

### 5.3 OIDC Authentication for Human Users

**Purpose:** Show the production-standard pattern for authenticating human users against an external identity provider rather than distributing individual client certificates.

**Syntax:**

```bash
# kube-apiserver flags (set at cluster provisioning time, not runtime)
--oidc-issuer-url=https://accounts.google.com
--oidc-client-id=kubernetes
--oidc-username-claim=email
--oidc-groups-claim=groups
```

```yaml
# ~/.kube/config — user entry using the oidc-login kubectl plugin
users:
  - name: jane-oidc
    user:
      exec:
        apiVersion: client.authentication.k8s.io/v1
        command: kubectl
        args:
          [
            "oidc-login",
            "get-token",
            "--oidc-issuer-url=https://accounts.google.com",
            "--oidc-client-id=kubernetes",
          ]
```

**Example usage and expected output:**

```bash
$ kubectl --user=jane-oidc get pods
# Opens a browser for interactive login the first time;
# subsequent calls reuse the cached, still-valid ID token
NAME       READY   STATUS    RESTARTS   AGE
web-app-1  1/1     Running   0          3h
```

**Production usage example:** OIDC lets an organization's existing identity provider remain the single source of truth for who exists and what groups they belong to — when an employee leaves and is deactivated in the identity provider, their cluster access is revoked automatically at the next token refresh, with no separate Kubernetes-specific offboarding step required.

**Common errors:** Forgetting that the API server's OIDC flags are set at cluster provisioning time (often not changeable without a control plane restart on self-managed clusters), and that managed offerings (EKS, AKS, GKE) each have their own distinct, provider-specific mechanism for wiring OIDC or IAM-based authentication rather than raw `--oidc-*` flags.

## 6. Production Usage Notes

- **X.509 client certificates have no revocation mechanism in standard Kubernetes** — a compromised certificate remains valid until it expires (there is no built-in CRL check against the client certificate authenticator), which is precisely why most production clusters prefer OIDC or short-lived tokens for human access over long-lived client certs.
- **`system:authenticated` and `system:unauthenticated` are implicit groups** every request is placed into based on whether authentication succeeded, and cluster-admins should be careful never to bind meaningful permissions to `system:unauthenticated` in any authorization policy.
- **Managed Kubernetes offerings frequently layer their own IAM integration on top of this model** (EKS's `aws-auth` ConfigMap mapping IAM principals to Kubernetes usernames/groups, GKE's Google Cloud IAM integration) — the underlying authentication chain concept still applies, but the exact configuration surface differs meaningfully across providers.

## 7. Security Considerations

- **Because X.509 certificates cannot be revoked without a CRL mechanism most clusters don't run, certificate-based human authentication should always use short expiry windows**, and any suspected compromise requires re-issuing the cluster's CA (a drastic, cluster-wide operation) if genuine revocation is required.
- **ServiceAccount tokens should be treated as sensitive credentials with the same seriousness as a Secret (§42)** — a leaked ServiceAccount token grants whatever RBAC permissions that ServiceAccount holds, for as long as the token remains valid, which is why bound, time-limited tokens (§76) are strongly preferred over legacy long-lived Secret-backed tokens.
- **Auditing which authentication modules are actually enabled on a cluster is a first-order security review step** — a cluster with the deprecated static token file authenticator still enabled, for instance, represents an unnecessary, often-forgotten attack surface that should be disabled in favor of OIDC or certificates.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                                       | Resolution Path                                                                                                |
| --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| `error: You must be logged in to the server (Unauthorized)`           | No authentication module accepted the request's credentials (expired cert, malformed token)        | Verify certificate/token validity and expiry; check `kubectl config view` for the active context's credentials |
| `Forbidden` immediately after a successful login                      | Authentication succeeded but no RoleBinding grants the resolved user/group any permission          | This is expected behavior, not a bug — proceed to configure RBAC (§75) for that identity                       |
| RBAC binding to a group never seems to apply                          | Certificate's `O` field, or OIDC group claim, doesn't match the group name used in the RoleBinding | `kubectl auth whoami` (if available) or decode the JWT/cert to confirm exact username/group strings            |
| ServiceAccount token in a Pod appears to work but stops after ~1 hour | Bound Service Account Token (§76) expired and wasn't refreshed by the client library               | Use a client library version that supports automatic token rotation via the projected volume mechanism         |

## 9. Best Practices

- Prefer OIDC for all human authentication in any organization with an existing identity provider, reserving X.509 client certificates for narrow bootstrap or break-glass scenarios.
- Never grant meaningful RBAC permissions directly to individual usernames when a group-based binding is available — group binding via OIDC claims scales identity management far better than per-user RoleBindings.
- Give every workload its own dedicated ServiceAccount rather than relying on a namespace's `default` ServiceAccount, so RBAC scoping and audit trails stay precise per workload.

## 10. Common Anti-Patterns / Mistakes

- **Distributing long-lived client certificates to every engineer** as the primary human authentication mechanism, with no practical revocation path if one is compromised.
- **Letting every Pod in a namespace run under the `default` ServiceAccount** rather than creating purpose-specific ServiceAccounts, which muddies both RBAC scoping and audit attribution.
- **Confusing a `401 Unauthorized` (authentication failure) with a `403 Forbidden` (authorization failure)** during troubleshooting — treating both as "permissions are broken" wastes time investigating the wrong layer.

## 11. Interview Questions

**🎯 Beginner:** _"Does Kubernetes have a built-in concept of a 'user' the way a traditional application does?"_
**Model answer:** No. Kubernetes has no `User` API object and no built-in user database. A "User" is simply whatever identity an authentication module resolves a request to — typically the Common Name of an X.509 client certificate or a claim from an OIDC ID token. ServiceAccounts, by contrast, are genuine API objects that Kubernetes fully manages, representing the identity of in-cluster workloads rather than humans.
_What the interviewer is probing for:_ Whether the candidate understands this is one of Kubernetes' most distinctive and frequently misunderstood design choices.

**🎯 Intermediate:** _"A user authenticates successfully but every `kubectl` command returns Forbidden. Walk through how you'd diagnose this."_
**Model answer:** A successful authentication followed by `Forbidden` means the request cleared the authentication stage — the API server knows who the caller is — but the authorization stage (RBAC by default) found no rule granting that identity the requested verb/resource combination. I'd confirm the exact resolved username and group with `kubectl auth can-i --list` or by inspecting the certificate/token claims, then check for a RoleBinding or ClusterRoleBinding (§75) targeting that exact username or group string, since a mismatch there (e.g., a typo in the group name, or binding to a Role in the wrong namespace) is the most common cause.
_What the interviewer is probing for:_ Clear separation of the authentication and authorization stages, and a methodical diagnostic approach rather than guessing.

**🎯 Senior:** _"Why can't a compromised X.509 client certificate be revoked in a typical Kubernetes cluster, and what does that imply for how you'd design human authentication?"_
**Model answer:** The X.509 client certificate authenticator built into the API server doesn't check a Certificate Revocation List or OCSP responder by default — once a certificate is signed by the cluster CA and hasn't expired, it remains valid regardless of whether the private key has since been compromised. The only genuine remediation short of waiting for expiry is rotating the cluster's CA entirely, which is a disruptive, cluster-wide operation. This strongly implies that certificate-based authentication should be reserved for short-lived, narrowly scoped use (bootstrap operations, break-glass access with tight expiry) rather than as the default mechanism for ongoing human access — OIDC, where the identity provider itself controls session validity and can immediately deactivate a compromised account, is the far more operationally sound choice at any real organizational scale.
_What the interviewer is probing for:_ Understanding of a specific, consequential Kubernetes security gap and the ability to translate it into a concrete architectural recommendation.

**🎯 Architect:** _"Design the authentication strategy for a platform serving both human engineers across multiple teams and dozens of automated CI/CD pipelines, spanning several clusters."_
**Model answer:** For humans, I'd standardize on OIDC against the organization's existing identity provider, with group claims mapped directly to RBAC groups (§75) so team membership managed in the identity provider automatically governs cluster access without any separate Kubernetes-side user administration — critically, this also means offboarding an employee in the identity provider immediately revokes their cluster access. For CI/CD systems, I'd avoid static, long-lived credentials entirely in favor of either short-lived Bound Service Account Tokens (§76) minted per pipeline run, or a workload-identity federation mechanism (IRSA on EKS, Workload Identity on GKE) that lets the CI system authenticate using its cloud-native identity rather than a Kubernetes-specific secret at all. Across multiple clusters, I'd keep the OIDC issuer and group-claim mapping consistent so a single RBAC policy model (§75) applies uniformly, and I'd audit periodically for any lingering static tokens or long-lived client certificates that predate this design, since those tend to accumulate as legacy exceptions if not actively tracked.
_What the interviewer is probing for:_ Ability to design a coherent, scalable identity strategy spanning both human and machine identities, anticipating operational lifecycle concerns (onboarding, offboarding, credential rotation) rather than just naming individual mechanisms.

## 12. Common Misconceptions

1. **"Kubernetes stores a list of users somewhere I can query."** There is no `User` API object; identity is entirely a byproduct of whichever authentication module accepted the request's credentials.
2. **"A successful login means the user can do things in the cluster."** Authentication only establishes identity; authorization (§74), an entirely separate stage, determines what that identity can actually do.
3. **"ServiceAccounts and Users are just two names for the same concept."** ServiceAccounts are real, namespaced API objects Kubernetes fully manages; Users are never represented as objects at all — they exist only as the output of an authentication module.
4. **"Revoking a compromised X.509 client certificate is straightforward."** Standard Kubernetes client certificate authentication has no revocation list check by default; short expiry and a CA rotation plan are the practical mitigations, not a simple revoke command.

## 13. 🔑 Key Takeaways

- Kubernetes has no built-in user database; every human identity comes from an external mechanism (certificates, OIDC, webhook), while ServiceAccounts are genuine, cluster-managed API objects for workload identity.
- The authentication chain tries every configured module in order and resolves successful requests to a username plus group set — nothing more, and nothing about permissions.
- OIDC is the production-standard mechanism for human authentication at organizational scale, because it delegates identity lifecycle management to an existing identity provider.
- X.509 client certificates have no built-in revocation mechanism, making them best suited to narrow, short-lived use rather than as the default for ongoing human access.
- Authentication and authorization are strictly separate stages — a `401` points at authentication, a `403` points at authorization (§74), and conflating the two wastes troubleshooting effort.

## 14. Related Concepts & What's Next

This section builds on §41–§42's ConfigMap and Secret consumption mechanics, which frequently underlie how OIDC client secrets, kubeconfig credentials, or bootstrap tokens are stored and injected. With identity now established, §74 covers what happens immediately after authentication succeeds: the authorization modes (RBAC, ABAC, Node, Webhook) that decide what an authenticated identity is actually permitted to do.

**Next Section:** §74 — `Section-74-Part10-Authorization-Modes-RBAC-ABAC-Node-Webhook.md`
