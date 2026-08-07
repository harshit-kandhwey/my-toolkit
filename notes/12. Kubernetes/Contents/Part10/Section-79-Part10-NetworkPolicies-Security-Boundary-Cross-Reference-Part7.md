# Section 79 (Part 10): NetworkPolicies as a Security Boundary

## 1. Definition

**Plain language:** [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md) covered what a Pod's own spec is allowed to declare — privileged mode, root execution, host namespace access. But even a perfectly hardened, Restricted-tier-compliant Pod can still be a wide-open network citizen, free to talk to (or be reached by) every other Pod in the cluster. Locking down what a Pod _is_ says nothing about what it can _reach_. That's a separate security boundary, and Kubernetes already has a dedicated mechanism for it: NetworkPolicy, covered mechanically back in [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md). This section revisits that exact same object, but through a security-and-threat-model lens rather than a networking-mechanics lens.

**Precise definition:** As established in [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md), a **NetworkPolicy** is a namespaced object restricting ingress/egress traffic for selected Pods via selectors, IP blocks, and ports, enforced entirely by the CNI plugin ([§49](../Part7/Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) and default-deny only once a matching policy exists for a given direction. Viewed as a **security boundary** rather than purely a connectivity-management tool, NetworkPolicy is the mechanism that limits **lateral movement** — an attacker who compromises one Pod (via a vulnerable dependency, a supply-chain issue, or a leaked credential) being unable to freely reach every other Pod, Service, and namespace in the cluster — and constrains **data exfiltration**, by restricting which external destinations a compromised Pod's outbound traffic can reach at all. This is the same object and the same additive, CNI-dependent enforcement model as [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md); nothing about the mechanism changes here, only the lens through which its design is evaluated.

## 2. Why This Matters

- **A cluster can be fully hardened at the Pod-spec level (Restricted-tier PSA from [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) and still suffer a trivial lateral-movement compromise**, because PSA has no visibility into network reachability at all — SecurityContext and NetworkPolicy are two genuinely independent security boundaries, and treating either as sufficient on its own is a common, exploitable gap.
- **Egress restriction — specifically preventing a compromised Pod from exfiltrating data to an arbitrary external destination — is a named, explicit requirement at the CKS level**, not an optional hardening nicety, and [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) already documented that egress control is the boundary most commonly neglected relative to ingress in real deployments.
- **The default-deny-then-allowlist design pattern from [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) is precisely the "assume breach" security posture** cluster hardening standards expect: if a Pod's blast radius on compromise is limited to only the specific, explicitly-allowlisted peers and destinations it was already permitted to reach, a single compromised workload cannot pivot cluster-wide.

🔑 **Key Takeaway:** NetworkPolicy (mechanically defined in [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) is the network-layer complement to Pod Security Admission ([§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) — where PSA governs what a Pod's spec may declare, NetworkPolicy governs what that Pod may actually reach over the network, and a default-deny, allowlist-only posture is what limits an attacker's lateral-movement and data-exfiltration blast radius after any single Pod is compromised.

## 3. Prerequisites and Dependencies

Builds directly on [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md) (Pod Security Admission — the Pod-spec-level security boundary this section's network-level boundary complements) and back-references [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) extensively, since this section reuses that section's exact object model, default-deny mechanics, and CNI enforcement dependency without repeating them mechanically. Forward-references [§80](./Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md), which covers secrets management integration — a further security boundary protecting what a Pod can access even once network reachability is otherwise permitted.

## 4. Architecture: Blast-Radius Containment Through Default-Deny

```text
                    WITHOUT NetworkPolicy (flat network, §55's baseline):

  Compromised Pod (frontend ns) ──────► reaches EVERY Pod, EVERY namespace
                                          - database Pods (backend ns)
                                          - internal admin APIs (platform ns)
                                          - arbitrary external IPs (exfiltration)

                    WITH default-deny + allowlist (this section's posture):

  ┌──────────────────────────────────────────────────────────────────────┐
  │ Compromised Pod (frontend ns, app=web)                               │
  │   egress allowed ONLY to:                                            │
  │     - DNS (kube-system, port 53)            [§55 DNS egress pattern]      │
  │     - api-gateway Service (backend ns, port 443)                     │
  │   egress DENIED to:                                                  │
  │     - database Pods directly                                         │
  │     - platform-admin namespace                                       │
  │     - any arbitrary external IP (no ipBlock rule permits it)         │
  └───────────────────────────────┬──────────────────────────────────────┘
                                  ▼
               Attacker's lateral movement and exfiltration options
               are limited to exactly what was already, deliberately
               allowlisted — not the entire flat cluster network.
```

- **This diagram is the direct security consequence of [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)'s mechanics** — the same `podSelector`/`ipBlock`/`policyTypes` fields, but read here as blast-radius containment rather than connectivity design.
- **The database Pods being unreachable directly from `frontend` even after compromise is the entire point** — a compromised web-tier Pod that can only reach an API gateway, never the database directly, has a materially smaller blast radius than one on a flat network.
- **The missing exfiltration path (no `ipBlock` rule permitting arbitrary external IPs) is what actually stops data leaving the cluster** — this is the specific egress-restriction gap [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) already flagged as commonly neglected, and it's the single most security-relevant NetworkPolicy design decision most teams skip.

## 5. Hands-On: Designing NetworkPolicy as a Threat-Model Boundary

### 5.1 Modeling a Compromised-Pod Scenario

**Purpose:** Show how an existing default-deny-plus-allowlist policy set (the exact pattern [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) established) limits reachability from a Pod assumed to already be compromised.

**Syntax:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: frontend-restricted-egress
  namespace: frontend
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: backend
          podSelector:
            matchLabels:
              app: api-gateway
      ports:
        - protocol: TCP
          port: 443
```

**Example usage and expected output:**

```bash
$ kubectl apply -f frontend-restricted-egress.yaml
networkpolicy.networking.k8s.io/frontend-restricted-egress created

$ kubectl exec -it web-pod -n frontend -- curl -m 3 http://database.backend.svc.cluster.local:5432
curl: (28) Connection timed out after 3000 milliseconds
# even a compromised shell inside this Pod cannot reach the database directly

$ kubectl exec -it web-pod -n frontend -- curl -m 3 https://evil-exfil-server.example.com
curl: (28) Connection timed out after 3000 milliseconds
# no ipBlock rule permits this destination — exfiltration path closed
```

**Production usage example:** Threat-modeling exercises for a namespace should explicitly test "what can a shell inside this Pod reach" against the actual policy set, not just review the YAML — the practical reachability test above is the same validation step a security review or CKS-style exam scenario expects, and it's a direct, hands-on application of [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)'s default-deny model to an actual compromise scenario.

**Common errors:** Assuming a NetworkPolicy that blocks _ingress_ into a sensitive Pod also protects that Pod's _own_ outbound reachability if compromised — as [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) established, ingress and egress are evaluated completely independently; a database Pod locked down against unwanted inbound connections can still freely reach out to an attacker-controlled destination if no egress policy exists for it at all.

### 5.2 Auditing Which Policies Actually Govern a Sensitive Namespace

**Purpose:** Apply [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)'s additive-model troubleshooting lesson specifically as a security audit step — confirming no overly broad policy elsewhere widens a sensitive namespace's actual exposure.

**Syntax:**

```bash
kubectl get networkpolicy --all-namespaces -o json | \
  jq -r '.items[] | select(.spec.podSelector == {} or (.spec.egress[]?.to == null)) | .metadata.namespace + "/" + .metadata.name'
```

**Example usage and expected output:**

```bash
$ kubectl get networkpolicy --all-namespaces -o json | jq -r '.items[] | select(.spec.podSelector == {} or (.spec.egress[]?.to == null)) | .metadata.namespace + "/" + .metadata.name'
staging/legacy-allow-all
```

**Production usage example:** This is precisely the additive-model audit step [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) identified — since NetworkPolicies never override or conflict with each other, a single forgotten, overly broad policy anywhere in the cluster (like `staging/legacy-allow-all` here) can silently undermine an otherwise carefully-restricted `payments` namespace if it happens to select the same Pods via a shared label; a security review must audit every policy touching sensitive Pods, not just the ones the payments team wrote themselves.

**Production usage example (continued):** In a CKS-style cluster hardening review, this audit step is typically automated as a recurring scheduled check ([§36](../Part5/Section-36-Part5-CronJobs-Scheduled-Job-Execution.md)'s CronJob mechanics, or a dedicated policy-linting job) feeding into the cluster's audit-log pipeline ([§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)), rather than performed manually before each review cycle.

**Common errors:** Auditing only the NetworkPolicies explicitly created by the team that owns a sensitive namespace, and missing a cluster-wide or platform-team-authored policy that also happens to select the same Pods — the additive model means every matching policy matters, regardless of which team or purpose it was originally written for.

## 6. Production Usage Notes

- **A security-driven NetworkPolicy review treats "what does this policy allow" and "what does this policy prevent" as equally important questions** — [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) covers the former (connectivity design) thoroughly; this section's contribution is making the latter (denied paths, and specifically the absence of an exfiltration path) an explicit, reviewed design goal rather than an incidental side effect.
- **NetworkPolicy as a security boundary is only as strong as the CNI plugin's actual enforcement ([§49](../Part7/Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md), [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) — this dependency does not change when viewed through a security lens**, and a cluster hardening checklist ([§81](./Section-81-Part10-Kubernetes-Security-Best-Practices-Checklist.md), this Part's capstone) must verify CNI enforcement explicitly rather than assume it.
- **Egress restriction to specific, named external CIDR blocks (rather than leaving egress fully open once ingress is restricted) is the single highest-leverage NetworkPolicy change for reducing exfiltration risk**, and is frequently the first gap identified in a CKS-oriented security review of an existing cluster.

## 7. Security Considerations

- **Lateral movement containment and data-exfiltration prevention are the two concrete security outcomes NetworkPolicy delivers**, and both depend entirely on a deliberate default-deny-then-allowlist design — the open-by-default posture [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) already warned against is a materially larger attack surface once viewed as "how far can a single compromised Pod actually reach."
- **NetworkPolicy provides no protection once traffic is already permitted** — it restricts _reachability_, not the _content_ of allowed traffic; a compromised Pod that's allowlisted to reach a legitimate API gateway can still abuse that legitimate, permitted path maliciously, which is why NetworkPolicy is one security layer among several (alongside PSA from [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md) and runtime detection tools like Falco, [§118](../Part15/Section-118-Part15-Runtime-Security-Threat-Detection-Falco.md)), not a complete solution on its own.
- **A NetworkPolicy security review must explicitly verify egress restriction to external IP ranges**, since ingress-only hardening (already flagged in [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) as a common half-measure) leaves the exfiltration path — arguably the more security-critical of the two directions — completely open.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                 | Cause                                                                                               | Fix                                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A compromised Pod can reach far more of the cluster than expected during an incident review             | No egress NetworkPolicy exists for that Pod, or one exists but only restricts ingress               | Apply an explicit egress-restricting policy scoped to only the destinations that workload legitimately needs                                                              |
| A security audit finds a sensitive namespace reachable from an unrelated team's Pods                    | An unrelated, overly broad NetworkPolicy elsewhere also selects the sensitive Pods (additive model) | Run a cluster-wide audit (`kubectl get networkpolicy --all-namespaces`) for any policy matching the sensitive Pods, not just the intended one                             |
| NetworkPolicy objects exist and look restrictive, but a compromise scenario shows no actual containment | CNI plugin doesn't enforce NetworkPolicy at all (e.g., Flannel alone)                               | Confirm CNI enforcement ([§49](../Part7/Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) before relying on any policy as an actual security control |
| Exfiltration to an arbitrary external IP succeeds from a Pod despite ingress being tightly restricted   | Egress was never restricted — ingress and egress are independent                                    | Add an explicit egress allowlist limited to required external destinations only                                                                                           |

## 9. Best Practices

- Explicitly test "what can a shell inside this Pod reach" against real deployed policy, not just review the YAML, as part of any security assessment.
- Treat egress restriction to named external destinations as a mandatory control for any Pod with legitimate external dependencies, not an optional addition after ingress is handled.
- Run the additive-model audit (`kubectl get networkpolicy --all-namespaces`) against every sensitive namespace as a recurring part of cluster security review, not a one-time check.
- Pair NetworkPolicy with PSA ([§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) explicitly in any hardening checklist — neither substitutes for the other.

## 10. Common Anti-Patterns / Mistakes

- **Treating Pod Security Admission ([§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) hardening as sufficient security posture on its own**, leaving network reachability completely unrestricted for an otherwise-hardened Pod.
- **Restricting ingress only and assuming that constitutes "the Pod is secured,"** leaving a compromised Pod free to exfiltrate data outward with no egress restriction at all.
- **Auditing only team-authored policies during a security review**, missing a broader, unrelated policy elsewhere that also matches the sensitive Pods under review via the additive model.

## 11. Interview Questions

**🎯 Beginner:** _"Why isn't Pod Security Admission alone sufficient to secure a cluster's workloads?"_
**Model answer:** PSA governs what a Pod's own spec is allowed to declare — whether it can run privileged, as root, with elevated capabilities — but it has no visibility into network reachability at all. A Pod that's fully compliant with the Restricted tier can still, by default, reach every other Pod and namespace in the cluster over the network. NetworkPolicy is the separate, complementary mechanism that restricts what a Pod can actually talk to, and both boundaries are needed together for real defense in depth.
_What the interviewer is probing for:_ Understanding that Pod-spec hardening and network-reachability restriction are two genuinely independent security boundaries, not redundant controls.

**🎯 Intermediate:** _"How does NetworkPolicy specifically limit the impact of a compromised Pod, assuming an attacker already has a shell inside it?"_
**Model answer:** Once a Pod is compromised, an attacker inherits whatever network reachability that Pod's egress rules permit — no more, no less. If the Pod is only allowlisted to reach DNS and one specific internal API gateway, the attacker's lateral movement options are limited to exactly that: they cannot pivot directly to a database Pod, an unrelated namespace, or exfiltrate to an arbitrary external destination, because no rule permits any of those paths. This is why default-deny-then-allowlist (from [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) matters specifically as a security posture, not just as tidy network design — it directly bounds the blast radius of any single Pod compromise.
_What the interviewer is probing for:_ Ability to reason about NetworkPolicy in terms of concrete attacker capability rather than abstract connectivity rules.

**🎯 Senior:** _"During a security review, you find a `payments` namespace with tight NetworkPolicy egress rules, yet a penetration test shows data was still exfiltrated from a Pod in that namespace. How do you investigate?"_
**Model answer:** Since NetworkPolicy is purely additive with no priority or override concept ([§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)), my first step is a cluster-wide audit of every NetworkPolicy that selects the affected Pods — `kubectl get networkpolicy --all-namespaces` filtered for anything matching the Pod's labels — not just the policies the `payments` team believes govern it; a broader, unrelated policy (perhaps a legacy or platform-wide one with an overly permissive `ipBlock` or empty selector) may also apply and is widening egress beyond what the team's own policy intended. Second, I'd verify the CNI plugin is actually enforcing NetworkPolicy in this cluster at all — a policy that looks correct on paper does nothing if enforcement isn't active. Third, I'd check whether the exfiltration path used a permitted, legitimate destination (e.g., the allowlisted API gateway) abused maliciously rather than a genuinely open network path — NetworkPolicy restricts reachability, not the content or intent of allowed traffic, so a legitimately-permitted path can still be abused if the workload behind it is itself compromised or malicious.
_What the interviewer is probing for:_ Systematic investigation combining the additive-model audit habit from [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md), healthy skepticism about CNI enforcement, and recognition that NetworkPolicy's scope is reachability, not content inspection.

**🎯 Architect:** _"Design the network-security boundary strategy for a multi-tenant cluster where tenants must not be able to reach each other's workloads or exfiltrate tenant data externally."_
**Model answer:** I'd mandate a namespace-per-tenant model with an automatically-applied default-deny-all NetworkPolicy (both directions) at namespace creation — likely enforced via the same admission-time automation used for the Pod Security Admission rollout in [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md), so a forgotten default-deny is never a viable outcome. On top of that floor, each tenant would explicitly declare their legitimate ingress (which shared platform Services they need to reach, if any) and egress (DNS at minimum, plus any approved external dependencies via named `ipBlock` allowlists) as reviewed, version-controlled manifests — treating these with the same change-review rigor RBAC ([§75](./Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) already gets. I'd explicitly forbid any cross-tenant `podSelector`/`namespaceSelector` rule outside a narrow, platform-team-reviewed shared-services allowlist, and I'd run a recurring, automated audit (the additive-model check from 5.2) across all tenant namespaces to catch any policy — tenant-authored or platform-authored — that unintentionally widens access beyond a tenant's own boundary. I'd confirm CNI enforcement ([§49](../Part7/Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) as a non-negotiable platform prerequisite, and I'd pair this network boundary with PSA ([§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) at Restricted tier and secrets isolation ([§80](./Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md), next) so that even if network reachability were somehow misconfigured, the blast radius is still bounded by what a Pod's spec and its accessible credentials would allow.
_What the interviewer is probing for:_ Platform-level design combining default-deny-by-default namespace provisioning, explicit reviewed allowlisting, recurring cross-cutting audits given the additive model, and correct layering with the other two security boundaries (PSA, secrets) covered across this Part.

## 12. Common Misconceptions

1. **"Pod Security Admission and NetworkPolicy cover overlapping ground."** They govern entirely independent boundaries — Pod-spec content versus network reachability — and neither substitutes for the other.
2. **"A NetworkPolicy that restricts ingress into a sensitive Pod also protects that Pod's own outbound reachability if it's compromised."** Ingress and egress are evaluated completely independently, exactly as established in [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md); an ingress-only policy leaves egress, and therefore exfiltration risk, fully open.
3. **"NetworkPolicy inspects the content of allowed traffic."** It does not — it restricts reachability only; a legitimately-permitted path can still be abused by a compromised or malicious workload behind it.
4. **"Auditing your own team's NetworkPolicy objects is sufficient to understand a namespace's actual exposure."** Because the model is purely additive, any policy anywhere in the cluster that also selects the same Pods affects real exposure, regardless of which team authored it.

## 13. 🔑 Key Takeaways

- NetworkPolicy (mechanically defined in [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) is the network-layer security boundary complementing PSA's ([§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)) Pod-spec-level boundary — both are needed together for real defense in depth.
- Viewed as a security control, NetworkPolicy's value is measured in lateral-movement containment and data-exfiltration prevention, both entirely dependent on a deliberate default-deny-then-allowlist design.
- Egress restriction to named external destinations is the single highest-leverage, most commonly neglected NetworkPolicy security control.
- The additive-model audit habit from [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) (checking every policy that selects a Pod, not just the intended one) is equally essential from a security-review perspective.
- NetworkPolicy restricts reachability, not the content of allowed traffic — it's one layer among several, not a complete security solution on its own.

## 14. Related Concepts & What's Next

This section revisited [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)'s NetworkPolicy mechanics (Part 7) through a security-and-threat-model lens, building on [§78](./Section-78-Part10-Pod-Security-Standards-Pod-Security-Admission.md)'s Pod Security Admission as the complementary Pod-spec-level boundary. Together, these two sections establish that securing a Kubernetes workload requires restricting both what a Pod's spec may declare and what that Pod may reach over the network. [§80](./Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md), next, adds a third boundary: what a Pod can actually access in terms of credentials and secret material, extending beyond native Kubernetes Secrets ([§42](../Part6/Section-42-Part6-Secrets-Types-Encoding-Vs-Encryption-Consumption.md)) into external secrets-management tooling.

**Next Section:** [§80](./Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md) — `Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md`
