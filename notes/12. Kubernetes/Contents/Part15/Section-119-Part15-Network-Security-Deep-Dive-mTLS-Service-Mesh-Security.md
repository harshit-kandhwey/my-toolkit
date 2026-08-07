# Section 119 (Part 15): Network Security Deep Dive: mTLS and Service Mesh Security

## 1. Definition

**Plain language:** [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) (Part 7) and [§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md) (Part 10) both established NetworkPolicy as the mechanism restricting which Pods can talk to which other Pods — a Layer 3/4 control based on IP, namespace, and port. But NetworkPolicy has no concept of the traffic's identity or content once a connection is permitted: it cannot verify that the Pod on the other end of an allowed connection is actually who it claims to be, and it cannot encrypt the traffic in transit. A permitted connection over a compromised or misconfigured CNI, or across a network segment an attacker has already gained a foothold on, is still readable and spoofable at that lower layer. This section covers the mechanism that closes that specific gap: mutual TLS (mTLS) enforced by a service mesh, which authenticates both ends of every connection cryptographically and encrypts the traffic itself, regardless of which network path it happens to travel.

**Precise definition:** **Mutual TLS (mTLS)** is a TLS handshake variant in which both the client and the server present and validate X.509 certificates, so each side cryptographically proves its identity to the other — as opposed to standard one-way TLS, where only the server authenticates itself to the client. A **service mesh** is an infrastructure layer that transparently injects a proxy (most commonly Envoy) as a sidecar container into every Pod, intercepting all inbound and outbound traffic for that Pod so the mesh's control plane can enforce mTLS, traffic policy, and observability uniformly across every workload without any application code change. **Istio**, the most widely deployed service mesh, ships a `PeerAuthentication` custom resource controlling whether mTLS is required, permissive, or disabled for a given namespace or workload, and its control plane (`istiod`) automatically provisions, rotates, and distributes the workload certificates each sidecar proxy uses — turning identity-based, encrypted-in-transit communication into a platform-enforced default rather than something every application team must implement itself.

## 2. Why This Matters

- **NetworkPolicy answers "can this Pod reach that Pod" but never "is the Pod on the other end of this connection actually who it claims to be, and is the traffic encrypted."** An attacker who compromises a node, a CNI component, or gains a position to intercept traffic on a permitted network path can still read or spoof plaintext service-to-service traffic even inside a tightly NetworkPolicy-restricted cluster — mTLS is the boundary that specifically closes this gap.
- **CKS's "Minimize Microservice Vulnerabilities" domain explicitly expects candidates to reason about encryption-in-transit and workload identity, not just network reachability** — a cluster hardened at every layer covered so far ([§113](./Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)–[§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)) but still passing plaintext, unauthenticated traffic between services has a materially incomplete security posture from an exam and real-world standpoint alike.
- **A service mesh's automatic certificate issuance and rotation removes the single most common reason mTLS is skipped in practice** — manually managing per-workload certificates at scale is operationally painful enough that teams often abandon it; automating that machinery is what makes mesh-wide mTLS actually sustainable.

🔑 **Key Takeaway:** NetworkPolicy ([§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md), [§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md)) restricts _which_ Pods can reach each other; mTLS via a service mesh adds _cryptographic identity verification and encryption_ on top of whatever connections NetworkPolicy already permits — the two are complementary layers, and a hardened cluster needs both, not either.

## 3. Prerequisites and Dependencies

Builds on [§118](./Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md) (Falco runtime threat detection — mTLS and mesh telemetry give Falco and other runtime tools richer, identity-attributed signal to alert on, rather than raw unauthenticated IP flows) and back-references [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) (Part 7, NetworkPolicy mechanics) and [§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md) (Part 10, NetworkPolicy as a security boundary) heavily, since this section's entire premise is adding an identity-and-encryption layer on top of the reachability boundary those two sections already established. Assumes familiarity with X.509 certificates and TLS handshake fundamentals, and with the sidecar Pod pattern from Part 4. Forward-references [§120](./Section-120-Part15-Secrets-Encryption-External-Secret-Stores-Deep-Dive.md), which covers secrets and encryption at a deeper level than Part 10's introduction.

## 4. Architecture Diagram

```text
                    WITHOUT service mesh (NetworkPolicy alone):

  Pod A (frontend) ──plaintext, unauthenticated──► Pod B (backend)
        │                                                │
        └── NetworkPolicy permits this connection ───────┘
            (reachability only — no identity check, no encryption)

                    WITH Istio service mesh + mTLS enforced:

  ┌───────────────────────────────┐        ┌──────────────────────────────┐
  │ Pod A (frontend)              │        │ Pod B (backend)              │
  │  ┌────────────┐  ┌─────────┐  │        │  ┌─────────┐  ┌───────────┐  │
  │  │ App        │─►│ Envoy   │──┼──mTLS──┼─►│ Envoy   │─►│ App       │  │
  │  │ container  │  │ sidecar │  │        │  │ sidecar │  │ container │  │
  │  └────────────┘  └─────────┘  │        │  └─────────┘  └───────────┘  │
  └───────────────┬───────────────┘        └───────────┬──────────────────┘
                  │                                    │
                  ▼                                    ▼
        ┌─────────────────────────────────────────────────────────┐
        │  istiod (mesh control plane)                            │
        │   - issues short-lived workload certs (SPIFFE identity) │
        │   - rotates certs automatically                         |
        │   - distributes PeerAuthentication policy (mTLS mode)   │
        └─────────────────────────────────────────────────────────┘

  Both sidecars authenticate each other via cert (identity check)
  Traffic between sidecars is encrypted (confidentiality + integrity)
  NetworkPolicy STILL governs whether this connection is permitted at all
```

- **The Envoy sidecar intercepts traffic transparently via `iptables` rules injected at Pod startup** — application containers are unaware the mesh exists; they make plain HTTP/gRPC calls, and the sidecar upgrades the connection to mTLS before it leaves the Pod.
- **`istiod` is the single source of workload identity in this diagram** — every sidecar's certificate is short-lived and tied to a SPIFFE-format identity derived from the Pod's ServiceAccount, meaning identity is cryptographically bound to the workload's Kubernetes-native identity, not a separately managed credential.
- **NetworkPolicy sits underneath this entire diagram, unchanged** — mTLS answers "is this the real Pod B, and is the traffic private," while NetworkPolicy still separately answers "is Pod A allowed to initiate this connection to Pod B at all." Removing NetworkPolicy does not make mTLS redundant, and vice versa.

## 5. Hands-On

### 5.1 Enabling Mesh-Wide mTLS with PeerAuthentication

**Purpose:** Enforce that every workload in a namespace only accepts mTLS-encrypted, mutually-authenticated connections, rejecting any plaintext traffic outright.

**Syntax:**

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: payments
spec:
  mtls:
    mode: STRICT
```

**Example usage:**

```bash
$ kubectl apply -f peerauthentication-strict.yaml
peerauthentication.security.istio.io/default created

$ kubectl exec -it curl-pod -n payments -- curl -v http://backend.payments.svc.cluster.local:8080
* TLS connection... established (sidecar transparently upgraded this)
< HTTP/1.1 200 OK

$ kubectl exec -it curl-pod -n other-ns -- curl -v http://backend.payments.svc.cluster.local:8080
curl: (56) Recv failure: Connection reset by peer
# a Pod without an Istio sidecar (no mesh identity) cannot establish the required mTLS handshake at all
```

**Production usage example:** A phased rollout typically starts with `mode: PERMISSIVE` — where a workload accepts both mTLS and plaintext simultaneously — while sidecars are progressively injected across every Pod in a namespace, then flips to `STRICT` only once telemetry confirms zero remaining plaintext traffic; jumping straight to `STRICT` before every workload has a sidecar breaks any Pod still lacking one.

**Common errors:** Applying `STRICT` mode before confirming every Pod in the namespace actually has the Envoy sidecar injected (checked via `kubectl get pod -o jsonpath='{.spec.containers[*].name}'` looking for `istio-proxy`) — traffic from any un-injected Pod is rejected outright, which looks identical to a NetworkPolicy denial in symptoms but has a completely different root cause and fix.

### 5.2 Authorizing Traffic by Workload Identity, Not Just IP

**Purpose:** Layer identity-based authorization on top of mTLS, restricting which authenticated service identities (not just IP/label selectors) may call a given workload.

**Syntax:**

```yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: backend-allow-frontend-only
  namespace: payments
spec:
  selector:
    matchLabels:
      app: backend
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/payments/sa/frontend-sa"
      to:
        - operation:
            methods: ["GET", "POST"]
```

**Example usage:**

```bash
$ kubectl apply -f authz-frontend-only.yaml
authorizationpolicy.security.istio.io/backend-allow-frontend-only created

$ kubectl exec -it frontend-pod -n payments -- curl backend.payments.svc.cluster.local:8080
HTTP/1.1 200 OK

$ kubectl exec -it some-other-pod -n payments -- curl backend.payments.svc.cluster.local:8080
RBAC: access denied
# some-other-pod's ServiceAccount identity does not match the allowed principal, even though NetworkPolicy permits the connection at the IP layer
```

**Production usage example:** `AuthorizationPolicy` principals are the mesh equivalent of RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md), Part 10) applied to service-to-service calls rather than API server requests — a compromised Pod that somehow gains network reachability to `backend` (a NetworkPolicy gap, or a misconfigured rule) still cannot successfully call it unless its ServiceAccount identity is on the explicit allowlist, giving a second, independent gate beyond NetworkPolicy.

**Common errors:** Writing `principals` against a ServiceAccount name that doesn't match the actual `serviceAccountName` on the calling Pod's spec — since mesh identity is derived directly from the Kubernetes ServiceAccount ([§76](../Part10/Section-76-Part10-ServiceAccounts-Tokens-Auto-Mounting-Bound-Tokens.md), Part 10), a typo or a Pod still running under `default` produces a silent, hard-to-diagnose 403 that has nothing to do with the application code itself.

## 6. Production Usage Notes

- **mTLS added by a service mesh does not replace NetworkPolicy ([§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md)) or RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) — it adds a third, independent boundary** operating at the transport-identity layer; a production hardening checklist should verify all three are configured, not treat any one as sufficient on its own.
- **Certificate rotation is fully automated by `istiod` and typically operates on short-lived certificates (often under 24 hours)**, meaning a compromised workload certificate has a naturally bounded window of validity — a meaningfully stronger posture than a long-lived, manually rotated TLS certificate an application team might otherwise manage by hand.
- **Sidecar injection adds real latency and resource overhead to every Pod in the mesh** — this is a legitimate production trade-off to budget for (extra CPU/memory requests per Pod, and an added network hop per call), not a free security upgrade, and should be load-tested before a mesh-wide `STRICT` rollout.

## 7. Security Considerations

- **`STRICT` mTLS mode is the meaningful security control; `PERMISSIVE` is a migration aid, not an end state** — a cluster left in `PERMISSIVE` indefinitely still accepts unauthenticated plaintext traffic from any workload that simply doesn't bother establishing mTLS, which is precisely the gap this section exists to close.
- **`AuthorizationPolicy` principals depend entirely on ServiceAccount identity being trustworthy** — if a namespace's RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) allows overly broad ServiceAccount token minting or reuse, an attacker who obtains a legitimate ServiceAccount's token can still pass mesh-level identity checks; mesh-level authorization is only as strong as the Kubernetes identity it's built on.
- **The mesh control plane (`istiod`) is itself a high-value target** — it holds the root of trust issuing every workload certificate in the mesh; compromising `istiod` is equivalent to compromising the entire mesh's identity system, so it deserves the same hardening rigor (RBAC restriction, network isolation) as the API server itself.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                             | Cause                                                                                                      | Fix                                                                                                                                                                                                |
| ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Connection reset by peer immediately after enabling `STRICT` mTLS                   | A calling Pod lacks the Envoy sidecar and cannot complete the required mTLS handshake                      | Confirm sidecar injection (`istio-proxy` container present) on every Pod before enforcing `STRICT`                                                                                                 |
| Requests return `RBAC: access denied` despite NetworkPolicy allowing the connection | An `AuthorizationPolicy` restricts by ServiceAccount principal and the caller's identity isn't allowlisted | Verify the calling Pod's `serviceAccountName` matches an allowed `principals` entry exactly                                                                                                        |
| mTLS appears enabled but traffic between two specific Pods is still plaintext       | One of the two Pods predates sidecar injection or was restarted without the mutating webhook active        | Restart the Pod so the injection webhook ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)-style mutating webhook) fires, or manually re-apply the sidecar |
| Mesh-wide latency increases noticeably after rollout                                | Every hop now traverses two additional Envoy proxies (client-side and server-side sidecar)                 | Budget sidecar CPU/memory in capacity planning; this is expected mesh overhead, not a misconfiguration                                                                                             |

## 9. Best Practices

- Roll out mTLS via `PERMISSIVE` mode first, confirm zero plaintext traffic via mesh telemetry, then flip to `STRICT` — never jump straight to `STRICT` cluster-wide.
- Pair `PeerAuthentication` (identity + encryption) with `AuthorizationPolicy` (fine-grained, identity-based authorization) rather than relying on mTLS alone to gate access.
- Treat `istiod`'s own security (RBAC access, network isolation, patching) with the same rigor as the API server, since it is the mesh's root of trust.
- Load-test sidecar-injected workloads before enforcing mesh-wide policy in production, since the added proxy hop is a real latency and resource cost.
- Keep `AuthorizationPolicy` principals synchronized with actual ServiceAccount assignments as workloads change — stale principal lists silently deny legitimate traffic or, worse, silently permit retired identities.

## 10. Common Anti-Patterns / Mistakes

- **Treating a service mesh as a replacement for NetworkPolicy ([§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md)) or RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md))**, rather than a third, complementary boundary operating at a different layer.
- **Leaving `PeerAuthentication` in `PERMISSIVE` mode indefinitely**, which provides no actual enforcement — any workload can simply continue using plaintext.
- **Enforcing `STRICT` mTLS before every Pod in scope has a sidecar injected**, causing legitimate traffic to fail with connection resets that look like an unrelated networking bug.
- **Granting `AuthorizationPolicy` access by overly broad principal patterns** (e.g., wildcarding an entire namespace) instead of naming specific ServiceAccounts, undermining the fine-grained authorization the policy exists to provide.

## 11. Interview Questions

**🎯 Beginner:** _"What does mTLS add on top of a NetworkPolicy that already restricts which Pods can talk to each other?"_
**Model answer:** NetworkPolicy answers whether a connection between two Pods is permitted at all, based on selectors, IP blocks, and ports — a Layer 3/4 reachability control. It says nothing about whether the Pod on the other end of a permitted connection is actually who it claims to be, or whether the traffic itself is encrypted. mTLS, enforced by a service mesh, adds exactly that: both sides present certificates and authenticate each other cryptographically, and the connection is encrypted in transit. A cluster can have perfect NetworkPolicy rules and still be passing plaintext, spoofable traffic between services — mTLS is the layer that closes that specific gap.
_What the interviewer is probing for:_ Clear separation between reachability control (NetworkPolicy) and identity/encryption control (mTLS) as genuinely different boundaries.

**🎯 Intermediate:** _"How does a service mesh like Istio manage workload certificates at scale without every application team handling TLS themselves?"_
**Model answer:** Istio's control plane, `istiod`, acts as the certificate authority for the entire mesh. When a Pod comes up with the Envoy sidecar injected, the sidecar requests a short-lived workload certificate from `istiod`, which issues one tied to a SPIFFE-format identity derived from the Pod's Kubernetes ServiceAccount. `istiod` automatically rotates these certificates well before expiry, and the entire process is transparent to the application — the app container makes ordinary HTTP or gRPC calls, and the sidecar handles the TLS handshake, certificate presentation, and validation on its behalf. This is what makes mesh-wide mTLS operationally sustainable; manually issuing and rotating certificates for every workload individually is exactly the burden that causes teams to skip mTLS in practice.
_What the interviewer is probing for:_ Understanding of the automated certificate lifecycle and why it's the key enabler for mTLS actually being adopted at scale.

**🎯 Senior:** _"A team enables `PeerAuthentication` with `STRICT` mode cluster-wide and immediately sees a spike in connection failures from several legacy workloads. How do you investigate and fix this?"_
**Model answer:** The first thing I'd check is whether the failing Pods actually have the Envoy sidecar injected — `STRICT` mode rejects any connection that can't complete the required mTLS handshake, and a Pod without a sidecar (perhaps because it was created before automatic injection was enabled on its namespace, or the namespace label enabling injection was never applied) has no way to participate in mTLS at all, producing exactly this symptom. I'd check `kubectl get pod -o jsonpath='{.spec.containers[*].name}'` across the affected Pods looking for the `istio-proxy` container, and cross-reference which namespaces have the `istio-injection=enabled` label. If sidecars are present but failures persist, I'd check for `AuthorizationPolicy` objects that might be independently denying the legacy workloads' ServiceAccount identity, since that failure mode looks similar but has a different root cause and fix. The remediation is either restarting the affected Pods so injection fires correctly, relaxing to `PERMISSIVE` mode temporarily while sidecars are rolled out across every legacy workload, or explicitly excluding a legacy namespace from mesh enforcement if it genuinely cannot run a sidecar, with a documented compensating control.
_What the interviewer is probing for:_ Systematic diagnosis distinguishing "no sidecar" from "authorization policy denial" as two different root causes with the same surface symptom, and awareness of a safe phased-rollout remediation path.

**🎯 Architect:** _"Design the network-identity security strategy for a platform running 200+ microservices across multiple teams, where you need both encryption-in-transit and fine-grained service-to-service authorization, without every team needing mesh expertise."_
**Model answer:** I'd deploy Istio (or an equivalent mesh) as a platform-managed capability, with automatic sidecar injection enabled at the namespace level by default rather than requiring individual teams to opt in — this ensures coverage is a platform guarantee, not something that depends on 200+ teams remembering to configure it correctly. I'd set a mesh-wide default `PeerAuthentication` in `STRICT` mode as the platform baseline, established only after a phased `PERMISSIVE`-to-`STRICT` migration validated via mesh telemetry that no workload was still relying on plaintext. For authorization, rather than each team hand-writing `AuthorizationPolicy` objects (error-prone at this scale), I'd build a thin platform layer — likely a small controller or a templated Helm chart ([§82](../Part11/Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md), Part 11) — that generates `AuthorizationPolicy` objects from a simpler, declarative "which services may call which" manifest each team maintains in their own repo, reviewed the same way RBAC bindings ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) are reviewed. I would treat `istiod` itself as a Tier-0 security asset: isolated via NetworkPolicy ([§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md)), access-restricted via RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)), monitored via the same audit-logging pipeline ([§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md), Part 12) covering the rest of the cluster, since compromising it compromises the identity root of trust for every one of the 200+ services. Finally, I'd layer this on top of, not instead of, NetworkPolicy-based reachability restriction and native Secrets/external-secrets discipline ([§120](./Section-120-Part15-Secrets-Encryption-External-Secret-Stores-Deep-Dive.md), next), so that identity, reachability, and credential access remain three independently enforced boundaries rather than a single point of failure.
_What the interviewer is probing for:_ Platform-level thinking about making a strong security default the path of least resistance for application teams, correct layering of mesh security alongside NetworkPolicy and RBAC rather than as a substitute, and recognition of the mesh control plane as a critical asset requiring its own hardening.

## 12. Common Misconceptions

1. **"A service mesh's mTLS makes NetworkPolicy unnecessary."** They operate at different layers — NetworkPolicy governs reachability, mTLS governs identity and encryption of whatever traffic reachability already permits — and both are needed together.
2. **"`PERMISSIVE` mode provides real security enforcement."** It accepts both mTLS and plaintext simultaneously specifically as a migration aid; only `STRICT` mode actually rejects unauthenticated plaintext traffic.
3. **"mTLS certificates in a service mesh need the same manual rotation discipline as a traditional TLS certificate."** `istiod` automates issuance and rotation entirely, using short-lived certificates tied to the workload's ServiceAccount identity, removing the manual burden that made mTLS impractical at scale before service meshes existed.
4. **"AuthorizationPolicy and NetworkPolicy accomplish the same thing."** NetworkPolicy authorizes by IP/label/namespace reachability at Layer 3/4; AuthorizationPolicy authorizes by cryptographically verified service identity at the mesh layer — a Pod can pass one check and fail the other.

## 13. 🔑 Key Takeaways

- mTLS via a service mesh adds cryptographic identity verification and transport encryption on top of whatever connections NetworkPolicy ([§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md), [§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md)) already permits — it is a complementary layer, not a replacement.
- `istiod` automates certificate issuance and rotation using short-lived, ServiceAccount-derived identities, which is what makes mesh-wide mTLS operationally sustainable at scale.
- `PeerAuthentication` in `STRICT` mode is the actual enforcement point; `PERMISSIVE` is only a migration aid and should never be treated as an end state.
- `AuthorizationPolicy` layers fine-grained, identity-based authorization on top of mTLS, providing a second independent gate beyond both NetworkPolicy and RBAC.
- The mesh control plane is a high-value asset that deserves the same hardening rigor as the API server, since it is the root of trust for every workload's identity in the mesh.

## 14. Related Concepts & What's Next

This section added a transport-identity and encryption-in-transit layer on top of the reachability boundary NetworkPolicy ([§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md), [§79](../Part10/Section-79-Part10-NetworkPolicies-Security-Boundary-Cross-Reference-Part7.md)) already established, using a service mesh's automatic mTLS and identity-based authorization to close a gap neither NetworkPolicy nor RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) addresses on its own. [§120](./Section-120-Part15-Secrets-Encryption-External-Secret-Stores-Deep-Dive.md), next, goes deeper into a related but distinct concern — protecting the confidentiality of data at rest and the credentials workloads consume — extending well beyond Part 10's introductory coverage of Secrets and external secrets tooling.

**Next Section:** [§120](./Section-120-Part15-Secrets-Encryption-External-Secret-Stores-Deep-Dive.md) — `Section-120-Part15-Secrets-Encryption-External-Secret-Stores-Deep-Dive.md`
