# Section 101 (Part 13): Networking Troubleshooting Scenarios (Unreachable Services, DNS Failures)

## 1. Definition

**Plain language:** §56's toolkit gave you the ordered checklist for "Pod can't reach Service." This section is the next level down — a set of specific, named failure scenarios that each look similar on the surface ("connection times out," "name doesn't resolve") but have distinct root causes and distinct fixes, and that trip up even engineers who already know the ordered checklist because the symptom doesn't obviously point at the actual layer that's broken.

**Precise definition:** This section catalogs **specific networking failure scenarios** that go beyond §56's general diagnostic flow — Endpoints objects that exist but never populate with the expected Pod IPs, Services that work within their own namespace but fail when accessed cross-namespace, and split-horizon DNS behavior where a name resolves differently (or not at all) depending on which Pod or node issues the query. Each scenario is walked through with the exact commands and exact output an engineer would see, following the same object-state-first, packet-capture-last discipline established in §56 and generalized in §100's structured methodology.

## 2. Why This Matters

- **A populated `Endpoints` object doesn't guarantee the underlying Pods are actually reachable** — endpoint population failures (wrong `targetPort`, a Pod stuck in a `NotReady` state that never surfaces in a shallow check) look identical to a healthy Service until you inspect the actual endpoint list contents, not just its non-empty-ness.
- **Cross-namespace access failures are frequently misattributed to NetworkPolicy** when the actual cause is a truncated DNS name (forgetting the `.namespace` suffix) or a Service that was never intended to be reachable outside its own namespace — jumping straight to a NetworkPolicy audit here wastes time that a thirty-second DNS query would have saved.
- **Split-horizon and stale-cache DNS issues are the least intuitive class of networking failure** in Kubernetes, because the same query can return different, individually "correct" answers depending on which CoreDNS Pod answered it or how long a client has cached a prior answer — these require recognizing the pattern, not just running more `dig` commands.

🔑 **Key Takeaway:** The scenarios in this section share one lesson — a Service or DNS query can look superficially healthy (Endpoints exist, DNS resolves to _something_) while still being broken in a way that only shows up when you inspect the actual contents of the answer, not just whether an answer was returned at all.

## 3. Prerequisites and Dependencies

Builds directly on §56 (in-cluster network troubleshooting toolkit) and §100 (Part 13's structured troubleshooting methodology), and assumes familiarity with §50 (Services), §52 (DNS/CoreDNS), and §55 (NetworkPolicy). Forwards into §102 (storage troubleshooting scenarios), continuing Part 13's scenario-by-scenario deep dive.

## 4. Architecture Diagram

```text
   Three networking scenarios and where they actually break

   Scenario A: Endpoints exist but traffic still fails
   ┌─────────────────────────────────────────────────────────────┐
   │ Service ── Selector matches Pods ──► Endpoints: 10.244.1.5  │
   │                                          │                  │
   │                                          ▼                  │
   │                          Pod is listening on 8080, but the  │
   │                          Service's targetPort says 8000     │
   │                          → connection refused, not timeout  │
   └─────────────────────────────────────────────────────────────┘

   Scenario B: Cross-namespace access
   ┌───────────────────────────────────────────────────────────────┐
   │  Pod (ns: team-a)  --curl svc-b-->  fails                     │
   │     tries:  http://svc-b            (implicit: svc-b.team-a)  │
   │     needs:  http://svc-b.team-b.svc.cluster.local             │
   │  → NXDOMAIN, misread as "Service down" instead of "wrong FQDN"│
   └───────────────────────────────────────────────────────────────┘

   Scenario C: Split-horizon / stale DNS cache
   ┌───────────────────────────────────────────────────────────────┐
   │  CoreDNS replica 1 (Node A)  ──► answers query, cached TTL    │
   │  CoreDNS replica 2 (Node B)  ──► ndots/search path differs,   │
   │                                  or cache not yet invalidated │
   │  Client Pod A queries replica 1: correct, fresh IP            │
   │  Client Pod B queries replica 2: stale IP (Pod already gone)  │
   └───────────────────────────────────────────────────────────────┘
```

- Scenario A is deliberately the "looks fine but isn't" case — every object-level check in §56's Step 1 passes, and the failure only becomes visible once you compare the Service's `targetPort` against the container's actual listening port.
- Scenario B is a pure naming-convention failure, not a connectivity failure at all — it resolves the instant the correct FQDN is used, which is the fastest possible confirmation of the root cause.
- Scenario C is the deepest of the three, requiring you to compare answers across multiple CoreDNS replicas or client Pods rather than trusting a single query's result as representative of the whole cluster.

## 5. Hands-On

### 5.1 Endpoints Populated but Traffic Still Fails (targetPort Mismatch)

**Purpose:** Recognize the specific failure where `kubectl get endpoints` shows healthy-looking IPs, so §56's Step 1 passes, but the connection still fails because the Service is forwarding to the wrong container port.

**Syntax:**

```bash
kubectl get endpoints <service> -n <namespace> -o wide
kubectl get svc <service> -n <namespace> -o jsonpath='{.spec.ports}'
kubectl get pod <pod> -n <namespace> -o jsonpath='{.spec.containers[0].ports}'
```

**Example usage:**

```bash
$ kubectl get endpoints web-svc -n default
NAME      ENDPOINTS            AGE
web-svc   10.244.1.5:8000      12m

$ kubectl get svc web-svc -n default -o jsonpath='{.spec.ports}'
[{"port":80,"protocol":"TCP","targetPort":8000}]

$ kubectl exec -it web-6d9c8-abcde -- curl -sv http://localhost:8000
curl: (7) Failed to connect to localhost port 8000: Connection refused
$ kubectl exec -it web-6d9c8-abcde -- ss -tlnp
State   Local Address:Port
LISTEN  0.0.0.0:8080
```

**Production usage example:** The Endpoints list looked entirely healthy (a real Pod IP and a real port), which is exactly why this scenario is dangerous — §56's Step 1 alone would pass, and only checking what port the container is _actually_ listening on (via `ss` or the container's own logs, not the Service spec) reveals the `targetPort: 8000` in the Service should have been `8080` to match the application's real listener.

**Common errors:** Trusting that a non-empty Endpoints entry means the port number in it is also correct — Endpoints inherit whatever `targetPort` the Service defines, they don't verify the target container is actually listening there.

### 5.2 Cross-Namespace Service Access Failing

**Purpose:** Diagnose the very common case where a Service works perfectly when accessed from within its own namespace but fails — often misdiagnosed as a NetworkPolicy block — when accessed from another namespace.

**Syntax:**

```bash
kubectl exec -it <pod> -n <source-ns> -- nslookup <svc>
kubectl exec -it <pod> -n <source-ns> -- nslookup <svc>.<target-ns>.svc.cluster.local
```

**Example usage:**

```bash
$ kubectl exec -it client-pod -n team-a -- nslookup billing-svc
Server:    10.96.0.10
** server can't find billing-svc.team-a.svc.cluster.local: NXDOMAIN

$ kubectl exec -it client-pod -n team-a -- nslookup billing-svc.team-b.svc.cluster.local
Server:    10.96.0.10
Name:      billing-svc.team-b.svc.cluster.local
Address:   10.96.44.12
```

**Production usage example:** Kubernetes' default DNS search path appends the _querying Pod's own namespace_ (here, `team-a`) to a bare short name, so `billing-svc` alone can only ever resolve a Service actually living in `team-a` — this is expected, correct behavior, not a bug, and the fix is always to use the fully-qualified `<svc>.<namespace>.svc.cluster.local` form (or at minimum `<svc>.<namespace>`) for any cross-namespace reference, hardcoded into application configuration rather than relying on the short name.

**Common errors:** Concluding a NetworkPolicy is blocking cross-namespace traffic and spending time auditing policies (§55) before first confirming with the fully-qualified name whether this is actually a naming issue — always test the FQDN form before touching NetworkPolicy.

### 5.3 Split-Horizon / Inconsistent DNS Answers Across the Cluster

**Purpose:** Recognize when different Pods (or the same Pod at different times) get different answers for the identical DNS query, and distinguish genuine CoreDNS replica inconsistency from ordinary client-side caching.

**Syntax:**

```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns -o wide
kubectl exec -it <pod-A> -- dig <svc>.<ns>.svc.cluster.local +short
kubectl exec -it <pod-B> -- dig <svc>.<ns>.svc.cluster.local +short
kubectl logs -n kube-system <coredns-pod> | grep -i error
```

**Example usage:**

```bash
$ kubectl get pods -n kube-system -l k8s-app=kube-dns -o wide
NAME                      NODE
coredns-5d78c9869d-abc12  node-a
coredns-5d78c9869d-xyz98  node-b

$ kubectl exec -it app-pod-on-node-a -- dig cache-svc.default.svc.cluster.local +short
10.96.20.15
$ kubectl exec -it app-pod-on-node-b -- dig cache-svc.default.svc.cluster.local +short
10.96.20.15
# identical Service IP is correct and expected — ClusterIP is stable

$ kubectl exec -it app-pod-on-node-a -- dig backend-headless.default.svc.cluster.local +short
10.244.3.9
10.244.3.14
$ kubectl exec -it app-pod-on-node-b -- dig backend-headless.default.svc.cluster.local +short
10.244.3.9
```

**Production usage example:** For a normal ClusterIP Service, every CoreDNS replica must return the identical answer since it's a single stable virtual IP — but for a **headless Service** (`clusterIP: None`, common with StatefulSets, §33), DNS returns the live set of backing Pod IPs directly, and a genuinely transient difference across replicas (as shown, one node's answer is missing a second Pod IP) usually means client-side DNS caching (`ndots`, the application's own resolver cache, or `dnsPolicy` settings) rather than CoreDNS itself being inconsistent — CoreDNS replicas all read from the same underlying API server state and don't diverge from each other under normal operation.

**Common errors:** Assuming any answer mismatch across Pods automatically means "CoreDNS is broken" without first checking whether the Service in question is headless (where the answer set legitimately changes as Pods come and go) versus a standard ClusterIP Service (where any mismatch would be a genuine, much rarer bug).

## 6. Production Usage Notes

- **`targetPort` mismatches, shown above, are especially common after a container image update** that changes the application's listening port without a corresponding update to the Service manifest — treating Service and Deployment manifests as a single reviewed unit during changes prevents this drift.
- **Cross-namespace FQDN requirements, shown above, are a frequent source of friction during namespace-per-team or namespace-per-environment migrations** — an application hardcoded to a bare Service name that worked fine as a monolith in one namespace breaks the moment teams or environments are split apart, making this worth an explicit check during any namespace restructuring project.
- **Headless Service DNS answers, shown above, are expected to change over time** as StatefulSet replicas scale or restart — building in appropriate client-side retry and re-resolution logic (rather than caching a resolved IP indefinitely) is a real application-design responsibility, not something CoreDNS alone can guarantee.

## 7. Security Considerations

- Cross-namespace DNS resolution succeeding by default (any Pod can resolve any Service's FQDN cluster-wide, regardless of namespace) means DNS name visibility is not a security boundary — NetworkPolicy (§55) is the actual enforcement point, and relying on "they don't know the FQDN" as an access control measure is not a real control.
- A `targetPort` misconfiguration that accidentally exposes a debug or admin port instead of the intended application port is a genuine security-relevant misconfiguration, not just a functional bug — worth flagging during the same review that catches the connectivity failure.
- CoreDNS logs and query patterns can reveal service topology information; restricting who can read `kube-system` logs is a reasonable extension of the general node/control-plane access discipline (§113, Part 15).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Cause                                                                                | Fix                                                                                                |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| Endpoints show a valid Pod IP, but `curl` returns "Connection refused" | `targetPort` on the Service doesn't match the port the container actually listens on | Check the container's real listening port with `ss -tlnp` inside the Pod; correct `targetPort`     |
| `NXDOMAIN` for a bare Service name used from a different namespace     | Default DNS search path only appends the querying Pod's own namespace                | Use the fully-qualified `<svc>.<namespace>.svc.cluster.local` form                                 |
| Different Pods get different DNS answers for the same headless Service | Expected behavior — headless Service DNS reflects the live, changing Pod set         | Confirm the Service is headless (`clusterIP: None`); ensure clients re-resolve rather than caching |
| Different Pods get different answers for a standard ClusterIP Service  | Genuine CoreDNS inconsistency (rare) or client-side stale cache                      | Check CoreDNS Pod logs/health; check client `dnsPolicy`/`ndots` and resolver cache behavior        |
| Cross-namespace access still fails with correct FQDN                   | NetworkPolicy blocking cross-namespace traffic                                       | Now proceed to the NetworkPolicy audit from §56's Step 4 — FQDN having ruled out naming            |

## 9. Best Practices

- Always verify a container's actual listening port with a tool run _inside_ the Pod (`ss`, application logs) rather than trusting the Service manifest's `targetPort` value as automatically correct.
- Hardcode fully-qualified `<svc>.<namespace>.svc.cluster.local` names in any application configuration that legitimately needs cross-namespace access, rather than relying on the default search-path behavior.
- When comparing DNS answers across Pods or nodes, first determine whether the Service in question is headless — this single check prevents most false "DNS is broken" conclusions in this scenario class.

## 10. Common Anti-Patterns / Mistakes

- **Treating a non-empty `Endpoints` entry as proof the Service is fully healthy**, without separately confirming the `targetPort` actually matches what the container listens on.
- **Jumping to a NetworkPolicy audit for a cross-namespace failure** before first testing with the fully-qualified DNS name, which resolves the large majority of these cases in seconds.
- **Assuming any cross-Pod DNS answer mismatch is a CoreDNS bug** without first checking whether the Service is headless, where a changing answer set is expected and correct behavior.

## 11. Interview Questions

**🎯 Beginner:** _"A Service's Endpoints list shows a valid Pod IP and port, but requests to it still fail with 'connection refused.' What would you check?"_
**Model answer:** I'd check what port the container is actually listening on from inside the Pod, using something like `ss -tlnp` or checking the application's own startup logs, and compare that against the Service's `targetPort`. A non-empty Endpoints entry only confirms the Selector matched a Ready Pod — it doesn't confirm the port number in that entry is one the container is actually listening on, and a mismatch here produces exactly this "connection refused" (not timeout) symptom.
_What the interviewer is probing for:_ Understanding that Endpoints existing and Endpoints being _correct_ are two different levels of confidence, and knowing to check the container's real listener directly.

**🎯 Intermediate:** _"An application in namespace `team-a` can't reach a Service in namespace `team-b` using just the Service's short name. Is this a bug?"_
**Model answer:** No — this is expected Kubernetes DNS behavior. The default DNS search path only automatically appends the querying Pod's own namespace, so a bare Service name like `billing-svc` can only resolve a Service that actually lives in `team-a`. Reaching a Service in another namespace requires the fully-qualified name, `billing-svc.team-b.svc.cluster.local` (or at minimum `billing-svc.team-b`). I'd confirm this is the actual issue by testing the FQDN form directly before considering anything about NetworkPolicy, since a huge fraction of "cross-namespace Service unreachable" tickets are actually just this naming convention being missed.
_What the interviewer is probing for:_ Knowing the default DNS search-path behavior precisely, and using it as the first, cheapest test before escalating to policy-level investigation.

**🎯 Senior:** _"You notice two Pods on different nodes get different DNS answers for the same Service name. Walk through how you'd determine whether this is a real problem."_
**Model answer:** The very first thing I'd check is whether the Service is headless (`clusterIP: None`) or a standard ClusterIP Service. For a headless Service backing a StatefulSet, DNS legitimately returns the current live set of backing Pod IPs, and a difference between two queries just seconds apart is normal if a Pod recently scaled or restarted — not a bug. For a standard ClusterIP Service, though, every CoreDNS replica should return the _identical_ stable virtual IP every time, since that IP doesn't change based on Pod state; a genuine mismatch there would point either at actual CoreDNS replica inconsistency (worth checking CoreDNS Pod logs and health directly) or, far more commonly, client-side DNS caching behavior (`ndots`, resolver cache, `dnsPolicy`) making it look like the cluster answered differently when actually the client just served a stale local answer.
_What the interviewer is probing for:_ Distinguishing headless-Service dynamic DNS from ClusterIP-Service stable DNS, and correctly attributing most apparent inconsistency to client-side caching rather than CoreDNS itself.

**🎯 Architect:** _"How would you reduce the frequency of these subtle networking scenarios (port mismatches, cross-namespace naming friction, DNS caching confusion) across many application teams?"_
**Model answer:** I'd push these checks as far left as possible rather than relying on each team to rediscover them during an incident. A CI-time manifest validation step can catch `targetPort`/container-port mismatches automatically by comparing the Service spec against the Pod template in the same manifest set, before it ever reaches production. For cross-namespace naming, I'd establish a platform convention requiring FQDNs for any inter-namespace reference in shared configuration templates or Helm charts, so it's baked into the scaffolding new services are built from rather than left to individual developer awareness. For DNS caching confusion around headless Services, I'd document the headless-vs-ClusterIP distinction directly in the platform's StatefulSet onboarding guide, since it's a recurring, predictable point of confusion for teams new to stateful workloads. More broadly, I'd feed each of these recurring scenario types back into the team's troubleshooting runbook (§105) so the pattern-recognition becomes institutional knowledge rather than something each engineer re-learns independently during their own incident.
_What the interviewer is probing for:_ Platform-level prevention (CI validation, scaffolding conventions, documentation) rather than only relying on better individual diagnostic skill, and translating recurring incident patterns into durable process improvements.

## 12. Common Misconceptions

1. **"A populated Endpoints list means the Service is fully working."** It only confirms the Selector matched a Ready Pod at the IP/port listed — it does not confirm that port is actually where the container is listening.
2. **"A Service should be reachable by its short name from any namespace."** By design, the default DNS search path only covers the querying Pod's own namespace; cross-namespace access requires the fully-qualified name.
3. **"Different DNS answers for the same name from different Pods always means CoreDNS is broken."** For headless Services this is expected, dynamic behavior; for standard ClusterIP Services, a mismatch is far more often client-side caching than actual CoreDNS inconsistency.
4. **"NetworkPolicy is the most likely cause of any cross-namespace access failure."** A simple missing namespace suffix in the queried name is a substantially more common cause and should be ruled out first.

## 13. 🔑 Key Takeaways

- Endpoints existing and Endpoints being correct are different levels of confidence — always verify the container's real listening port matches the Service's `targetPort`.
- Cross-namespace Service access requires the fully-qualified `<svc>.<namespace>.svc.cluster.local` name by design; test this before auditing NetworkPolicy.
- Headless Services return a dynamic, changing set of Pod IPs by design — don't mistake this for CoreDNS inconsistency.
- Apparent DNS answer mismatches for standard ClusterIP Services are usually client-side caching, not actual cluster-level DNS breakage.
- Push these checks left into CI validation and platform scaffolding conventions rather than relying on each team rediscovering them during an incident.

## 14. Related Concepts & What's Next

This section extends §56's general networking troubleshooting toolkit with specific, commonly-misdiagnosed scenarios, building on §50 (Services), §52 (DNS), and §55 (NetworkPolicy), and following the structured methodology established in §100. §102 continues Part 13's scenario-driven approach into storage troubleshooting next.

**Next Section:** §102 — `Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md`
