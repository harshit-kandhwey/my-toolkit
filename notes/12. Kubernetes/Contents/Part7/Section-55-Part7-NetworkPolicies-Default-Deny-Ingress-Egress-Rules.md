# Section 55 (Part 7): NetworkPolicies: Default-Deny Posture, Ingress/Egress Rule Design

## 1. Definition

**Plain language:** By default, every Pod in a Kubernetes cluster can talk to every other Pod, cluster-wide, regardless of namespace — a flat, fully-open network model that is convenient for getting started but is a real security liability once a cluster hosts more than one team or workload of differing sensitivity. NetworkPolicy lets you restrict that.

**Precise definition:** A **NetworkPolicy** is a namespaced Kubernetes API object that specifies allowed **ingress** (incoming) and/or **egress** (outgoing) traffic for a selected set of Pods, based on Pod/namespace selectors, IP block (CIDR) ranges, and ports/protocols. NetworkPolicies are **additive and default-deny once any policy selects a Pod for a given direction** — a Pod with zero applicable NetworkPolicies allows all traffic in that direction (the cluster default), but a Pod matched by at least one ingress-type NetworkPolicy allows _only_ traffic explicitly permitted by the union of all matching policies' rules, denying everything else by default. Critically, **NetworkPolicy enforcement is entirely dependent on the CNI plugin** — the API object can be created in any cluster, but it has zero effect unless the installed CNI plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) actually implements NetworkPolicy enforcement (Calico and Cilium do; Flannel alone does not).

## 2. Why This Matters

- **NetworkPolicy enforcement requires CNI plugin support, and this is not universal — a very easy-to-miss gap.** A cluster running Flannel alone can have NetworkPolicy objects applied via `kubectl apply` with zero errors and zero actual enforcement, since Flannel has no NetworkPolicy controller — the objects silently do nothing, which is a materially different failure mode from a clear rejection or error ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md) covers this CNI capability gap at install-time decision level).
- **The "default-allow-all, then restrict" starting posture is itself a security anti-pattern for anything beyond a single-team dev cluster** — moving to an explicit default-deny baseline ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)'s CKS network security depth builds on exactly this pattern) and then allowlisting only necessary traffic is the standard production security posture, not an unusual hardening step.
- **NetworkPolicy rules are purely additive across multiple objects targeting the same Pods** — there is no explicit "deny" rule type; achieving a deny-by-default posture means creating a policy that selects Pods with empty rule lists for a direction, then adding further policies that explicitly allow only what's needed, and understanding this additive-only model is essential to avoid an unintentionally over-permissive or contradictory-seeming policy set.

🔑 **Key Takeaway:** NetworkPolicy provides namespace-scoped, additive-only ingress/egress traffic restriction that is only as real as the CNI plugin's enforcement support underneath it — always verify the plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) supports NetworkPolicy before relying on it, and design deliberately from a default-deny baseline outward rather than an open-by-default posture restricted after the fact.

## 3. Prerequisites and Dependencies

Builds directly on [§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md) (CNI plugin selection — NetworkPolicy enforcement is a plugin-dependent capability, not guaranteed by the API's existence) and references forward to [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) (Part 15, CKS network security depth, which builds substantially on this section's default-deny model).

## 4. Architecture Diagram

```text
                     Default cluster behavior (no NetworkPolicy):
     Pod A (ns: frontend) ────────────► Pod B (ns: backend) : ALLOWED
     Pod C (ns: anything) ────────────► Pod B (ns: backend) : ALLOWED
                     (flat, fully-open network — any Pod reaches any Pod)

                     Once a NetworkPolicy selects Pod B for ingress:

     ┌────────────────────────────────────────────────────────────────────────┐
     │ NetworkPolicy: backend-allow-from-frontend                             │
     │   podSelector: app=backend         (selects Pod B)                     │
     │   policyTypes: [Ingress]                                               │
     │   ingress:                                                             │
     │     - from:                                                            │
     │         - podSelector: { app: frontend }                               │
     │           namespaceSelector: { kubernetes.io/metadata.name: frontend } │
     │       ports: [{ port: 8080, protocol: TCP }]                           │
     └────────────────────────────────────────────────────────────────────────┘

     Pod A (ns: frontend, app=frontend) ──────► Pod B : ALLOWED (matches rule, port 8080)
     Pod C (ns: anything, app=other)   ──────► Pod B : DENIED  (no matching rule — default-deny now active)
```

- **The moment any NetworkPolicy's `podSelector` matches a Pod for a given `policyTypes` direction, that Pod's default flips from allow-all to deny-all-except-explicitly-permitted** for that direction — an unselected Pod, or a direction not listed in `policyTypes`, remains fully open.
- **`ingress` and `egress` are evaluated independently** — a Pod can have an ingress-restricting policy with no egress policy at all, meaning its outbound traffic remains completely unrestricted even while its inbound traffic is locked down; a common, easy-to-miss half-measure.
- **Multiple NetworkPolicies targeting the same Pod are additive (logical OR)**, never conflicting or overriding each other — there is no policy priority or explicit deny rule; the union of all matching allow-rules across every applicable policy defines what's permitted.

## 5. Hands-On: Building a Default-Deny Posture

### 5.1 Namespace-Wide Default-Deny (Both Directions)

**Purpose:** Establish the deliberate security baseline — deny all ingress and egress in a namespace by default, then allowlist explicitly afterward.

**Syntax:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: backend
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

**Example usage and expected output:**

```bash
$ kubectl apply -f default-deny-all.yaml
networkpolicy.networking.k8s.io/default-deny-all created

$ kubectl exec -it test-pod -n backend -- curl -m 3 http://other-svc.backend.svc.cluster.local
curl: (28) Connection timed out after 3000 milliseconds
```

**Production usage example:** This exact manifest — empty `podSelector` (matches every Pod in the namespace) with both `policyTypes` and no rules listed — is the standard, first object applied when hardening a namespace, deliberately breaking all traffic in and out until explicit allow rules (5.2, 5.3) are added back one at a time.

**Common errors:** Applying this in a namespace whose CNI plugin doesn't support NetworkPolicy enforcement (e.g., Flannel-only) produces zero effect and zero errors — always confirm enforcement is actually active ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) before treating the absence of connectivity issues as evidence a default-deny policy is working; conversely, on an enforcing plugin, applying this without a rollout plan can cause an unplanned outage of all namespace traffic.

### 5.2 Allowing Specific Ingress Traffic

**Purpose:** Re-permit only the traffic actually required, on top of the default-deny baseline from 5.1.

**Syntax:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-frontend-to-api
  namespace: backend
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: frontend
          podSelector:
            matchLabels:
              app: frontend
      ports:
        - protocol: TCP
          port: 8080
```

**Example usage and expected output:**

```bash
$ kubectl apply -f allow-frontend-to-api.yaml
networkpolicy.networking.k8s.io/allow-frontend-to-api created

$ kubectl exec -it frontend-pod -n frontend -- curl -m 3 http://api-svc.backend.svc.cluster.local:8080/health
{"status":"ok"}

$ kubectl exec -it other-pod -n other-ns -- curl -m 3 http://api-svc.backend.svc.cluster.local:8080/health
curl: (28) Connection timed out after 3000 milliseconds
```

**Production usage example:** Combining a `namespaceSelector` and `podSelector` inside the same `from` entry (as shown) means "Pods labeled `app=frontend` specifically within the `frontend` namespace" — a common precision requirement, since a `namespaceSelector` alone would permit _any_ Pod in that namespace, not just the intended one.

**Common errors:** Placing `namespaceSelector` and `podSelector` as two separate list items under `from` (rather than combined in one) changes the meaning from AND to OR — matching Pods in the target namespace _or_ Pods anywhere with the label, a subtle YAML-structuring mistake that silently over-permits access.

### 5.3 Restricting Egress to DNS and a Specific External CIDR

**Purpose:** Show a realistic egress policy — Pods almost always need at least DNS ([§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)) egress permitted explicitly, which is easy to forget once egress is default-denied.

**Syntax:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-egress-dns-and-external
  namespace: backend
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector: {}
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - ipBlock:
            cidr: 203.0.113.0/24
      ports:
        - protocol: TCP
          port: 443
```

**Example usage and expected output:**

```bash
$ kubectl apply -f api-egress-dns-and-external.yaml
networkpolicy.networking.k8s.io/api-egress-dns-and-external created

$ kubectl exec -it api-pod -n backend -- nslookup partner-api.example.com
Server:    10.96.0.10
Address:   10.96.0.10#53
Name:      partner-api.example.com
Address:   203.0.113.50

$ kubectl exec -it api-pod -n backend -- curl -m 3 https://203.0.113.50
{"status":"ok"}
```

**Production usage example:** Forgetting the DNS egress rule (port 53 UDP/TCP) after applying a default-deny egress policy is one of the single most common causes of "everything broke after we added NetworkPolicy," since Pods can no longer resolve any name — including in-cluster Service names — even though the rest of the network path might be perfectly fine.

**Common errors:** Omitting the DNS rule (or scoping the `namespaceSelector: {}` for DNS too narrowly to just `kube-system`) breaks all name resolution for the selected Pods, producing symptoms that look like a DNS outage ([§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)) but are actually an egress NetworkPolicy misconfiguration.

## 6. Production Usage Notes

- **A namespace-wide default-deny policy should always be rolled out with an explicit, tested list of required allow-rules ready beforehand**, ideally validated in staging first — applying default-deny to a live production namespace without pre-staged allow rules is a guaranteed, immediate outage.
- **NetworkPolicy has no explicit "deny" rule and no rule priority/ordering** — all matching policies for a Pod are additive; achieving true isolation means carefully avoiding accidentally-broad allow rules elsewhere, since one over-permissive policy anywhere that selects the same Pod widens access regardless of how tightly other policies are written.
- **Egress control is frequently neglected relative to ingress** — many teams default-deny ingress but leave egress wide open, missing a real security control (e.g., preventing a compromised Pod from exfiltrating data to an arbitrary external IP) that egress policies specifically exist to provide.

## 7. Security Considerations

- NetworkPolicy enforcement is entirely dependent on the CNI plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) — treating a cluster as "secured by NetworkPolicy" without first confirming the plugin actually enforces it is a false sense of security with real risk.
- Default-deny-egress is a meaningful control against data exfiltration and lateral movement from a compromised Pod, and is a specific, named requirement in CKS-level cluster hardening ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)) — not an optional nicety.
- Because policies are additive with no explicit deny, a single overly broad policy (e.g., an accidentally empty `from`/`to` list, which matches everything) anywhere in a namespace can silently undermine an otherwise carefully-restricted set of other policies.

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                                            | Resolution Path                                                                                                                                                                              |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| NetworkPolicy applied, but traffic behaves as if nothing changed  | CNI plugin doesn't support NetworkPolicy enforcement (e.g., Flannel alone)              | Confirm the CNI plugin's NetworkPolicy support ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)); switch to or add an enforcing plugin (Calico, Cilium) if not |
| All Pod-to-Pod traffic broke after applying a default-deny policy | No allow-rules staged before the default-deny policy was applied                        | Add the required allow-rules immediately; always stage/test allow-rules before default-deny rollout going forward                                                                            |
| DNS resolution fails only after adding an egress NetworkPolicy    | Missing explicit port-53 (UDP/TCP) egress allow-rule                                    | Add a DNS-egress rule, as shown above, permitting traffic to the cluster DNS Service/`kube-system` namespace                                                                                 |
| A Pod is reachable from a namespace that should be restricted     | An unrelated, overly broad NetworkPolicy elsewhere also selects the same Pod (additive) | Audit all NetworkPolicies selecting the Pod (`kubectl get networkpolicy --all-namespaces`), not just the intended one                                                                        |

## 9. Best Practices

- Confirm the cluster's CNI plugin actually enforces NetworkPolicy before designing any policy strategy around it — this single check should precede all further NetworkPolicy work.
- Design from an explicit default-deny baseline (both ingress and egress) per namespace, adding narrowly-scoped allow rules for only the traffic that's actually required, rather than starting from the open-by-default posture and trying to restrict it after the fact.
- Always include DNS egress (port 53) in any egress-restricting policy set, and test allow-rules in staging before applying a default-deny policy to any production namespace.

## 10. Common Anti-Patterns / Mistakes

- **Assuming NetworkPolicy objects are enforced simply because they were applied without error**, without verifying the CNI plugin actually supports enforcement.
- **Default-denying ingress only, while leaving egress completely open**, missing a meaningful control against compromised-Pod data exfiltration and lateral movement.
- **Applying a namespace-wide default-deny policy to production without first staging and testing the required allow-rules**, causing an avoidable, self-inflicted outage.

## 11. Interview Questions

**🎯 Beginner:** _"What does a Kubernetes cluster's Pod-to-Pod network behavior look like by default, with no NetworkPolicy objects applied?"_
**Model answer:** By default, Kubernetes has a flat network model — every Pod can reach every other Pod, across every namespace, on any port, with no restriction at all. NetworkPolicy objects are what introduce restriction; without any applied, the cluster is fully open by default, which is convenient for simple or single-team clusters but a real security gap for anything hosting multiple teams or workloads with differing trust levels.
_What the interviewer is probing for:_ Correct baseline understanding that Kubernetes networking is open-by-default, not secure-by-default.

**🎯 Intermediate:** _"Explain how NetworkPolicy's default-deny behavior actually gets triggered, and why an empty egress policy set combined with an ingress-only policy can be a mistake."_
**Model answer:** A Pod's traffic in a given direction (ingress or egress) only becomes default-deny once at least one NetworkPolicy's `podSelector` matches that Pod and lists that direction in `policyTypes` — an unselected Pod, or a direction never referenced by any matching policy, stays fully open. This means a team can apply an ingress-restricting policy, see it work as intended, and mistakenly believe the Pod is now "secured," while its egress traffic remains completely unrestricted since no policy ever touched that direction — a common half-measure that misses controls like preventing a compromised Pod from exfiltrating data outward.
_What the interviewer is probing for:_ Precise understanding of the per-direction, per-Pod-selector trigger mechanism, and awareness that ingress-only hardening is incomplete.

**🎯 Senior:** _"A team applied a NetworkPolicy intended to restrict access to a sensitive backend Service, but during a security review you find another team's Pod, in an unrelated namespace, can still reach it. How would you investigate?"_
**Model answer:** Since NetworkPolicies are purely additive with no explicit deny or priority mechanism, my first step would be listing every NetworkPolicy across the cluster that selects the backend Pods (`kubectl get networkpolicy --all-namespaces` combined with checking each policy's `podSelector`), not just the one the team believes is responsible for restricting access — it's very possible a separate, broader policy (perhaps an older or forgotten one, or one with an accidentally empty or overly broad `from`/`namespaceSelector`) also matches the same Pods and is granting access the intended policy never meant to allow. I'd also independently confirm the CNI plugin is actually enforcing NetworkPolicy at all in this cluster, since if it isn't, none of the applied policies are doing anything and the "leak" is actually the absence of enforcement entirely, not a specific policy conflict.
_What the interviewer is probing for:_ Understanding of the additive-only model's implication (must audit _all_ matching policies, not just the "intended" one) and healthy skepticism about whether enforcement is even active.

**🎯 Architect:** _"You're setting a platform-wide NetworkPolicy standard for a cluster hosting dozens of independent teams with varying trust levels. What's your baseline design?"_
**Model answer:** I'd mandate a namespace-scoped default-deny-all policy (both ingress and egress) applied automatically to every new namespace, likely via a policy-as-code or admission-time automation rather than relying on each team to remember it, since a forgotten default-deny is effectively a fully-open namespace by omission. On top of that baseline, I'd require every team to explicitly declare their needed ingress (which namespaces/Pods can reach them) and egress (DNS at minimum, plus any legitimate external dependencies) as versioned, reviewed manifests, treating NetworkPolicy definitions with the same change-review rigor as RBAC changes. I'd also mandate confirming the cluster's CNI plugin supports enforcement as a non-negotiable platform requirement before any of this is meaningful, and I'd periodically audit for overly broad policies cluster-wide (empty `from`/`to` selectors, accidentally cluster-scoped access), since the additive-only model means any one team's overly permissive policy can undermine the isolation of others sharing the same cluster.
_What the interviewer is probing for:_ Platform-level thinking about defaulting to secure-by-default at namespace creation time, treating NetworkPolicy as reviewed infrastructure rather than an optional per-team afterthought, and awareness of the additive model's cluster-wide audit implications.

## 12. Common Misconceptions

1. **"Applying a NetworkPolicy guarantees it's enforced."** Enforcement depends entirely on CNI plugin support ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)); on a non-enforcing plugin, applied policies have zero actual effect.
2. **"NetworkPolicy has explicit deny rules."** It does not — the model is purely additive allow-rules; isolation comes from the absence of any matching allow-rule, not from an explicit deny.
3. **"Restricting ingress is sufficient hardening."** Egress is evaluated completely independently; an ingress-only policy leaves outbound traffic (including potential data exfiltration paths) fully unrestricted.
4. **"Multiple NetworkPolicies on the same Pod can conflict or override each other."** They cannot — all matching policies' allow-rules are combined additively (logical OR); there is no concept of one policy overriding another.

## 13. 🔑 Key Takeaways

- NetworkPolicy restricts ingress/egress traffic per-Pod via selectors, IP blocks, and ports, but only becomes default-deny in a direction once at least one matching policy references that direction.
- Enforcement is entirely CNI-plugin-dependent — always confirm the plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) actually supports it before relying on any NetworkPolicy for real security.
- The model is purely additive with no explicit deny or priority — auditing "all policies selecting this Pod," not just the one you wrote, is essential when troubleshooting unexpected access.
- Egress restriction (especially remembering DNS on port 53) is frequently neglected relative to ingress, despite being a meaningful control against compromised-Pod exfiltration.
- Default-deny should be designed from the start with pre-staged, tested allow-rules — applying it to a live namespace without preparation causes an immediate, self-inflicted outage.

## 14. Related Concepts & What's Next

[§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md) covers the CNI plugin layer this section's enforcement entirely depends on, and [§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)'s DNS coverage explains exactly why DNS egress rules are so often the missing piece in a new egress policy. [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) returns to NetworkPolicy as part of full CKS-level cluster and network security hardening, building directly on this section's default-deny model. [§56](./Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) closes out Part 7 by folding NetworkPolicy-aware diagnosis into the complete in-cluster network troubleshooting toolkit.

**Next Section:** [§56](./Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) — `Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md`
