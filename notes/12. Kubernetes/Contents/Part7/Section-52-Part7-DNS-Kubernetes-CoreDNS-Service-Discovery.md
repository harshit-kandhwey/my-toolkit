# Section 52 (Part 7): DNS in Kubernetes: CoreDNS, Service Discovery, and DNS Record Types

## 1. Definition

**Plain language:** Applications shouldn't have to hardcode a Service's virtual IP address to talk to it — instead, every Pod gets a working DNS resolver pointed at an in-cluster DNS server, so code can simply refer to a Service by a predictable, human-readable name and get back the correct IP automatically.

**Precise definition:** **CoreDNS** is the default in-cluster DNS server for Kubernetes, running as a Deployment (typically in `kube-system`) that watches the API server for Service and Pod changes and dynamically serves DNS records reflecting cluster state. Every Pod's `/etc/resolv.conf` is configured (via kubelet) to use the CoreDNS Service's ClusterIP as its nameserver, enabling **service discovery** — resolving a predictable DNS name to a Service's ClusterIP (or, for headless Services, directly to backing Pod IPs) without any application-level configuration of IP addresses.

## 2. Why This Matters

- **DNS is the mechanism that makes the Service abstraction ([§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md)) actually usable by applications without extra plumbing.** A Service's ClusterIP is stable, but an application still needs to know it — CoreDNS is what lets a Pod simply resolve `my-service.my-namespace.svc.cluster.local` (or just `my-service` from within the same namespace) rather than requiring the IP to be injected through some other mechanism.
- **Headless Services (`clusterIP: None`) change DNS behavior fundamentally, not just cosmetically** — instead of resolving to one stable virtual IP, a headless Service's DNS name resolves directly to the IP addresses of all backing Pods, which is the exact mechanism StatefulSets rely on for stable, individually-addressable Pod network identities.
- **DNS failures are one of the most common "networking" symptoms that are actually application-layer or CoreDNS-specific**, not CNI ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) or kube-proxy ([§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md)) problems — correctly distinguishing "Service unreachable by IP" from "Service unreachable by name" is a critical first triage step covered in the troubleshooting toolkit ahead ([§56](./Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)).

🔑 **Key Takeaway:** CoreDNS dynamically serves DNS records reflecting live cluster state, giving every Pod predictable, name-based service discovery instead of requiring hardcoded IPs — and understanding its naming convention and headless-Service behavior precisely is essential for correctly diagnosing whether a connectivity problem is a DNS issue or something further down the network stack.

## 3. Prerequisites and Dependencies

Builds directly on [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) (Services — the objects whose ClusterIPs CoreDNS resolves names to) and [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) (kubelet, which configures each Pod's `/etc/resolv.conf` to point at CoreDNS).

## 4. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                         kube-system namespace                   │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  CoreDNS Deployment (2+ replica Pods)                   │   │
│   │  - watches API server for Service/Pod/Endpoint changes  │   │
│   │  - serves DNS records dynamically, no static zone files │   │
│   └───────────────────────────────┬─────────────────────────┘   │
│                                    │                            │
│   ┌────────────────────────────────▼────────────────────────┐   │
│   │  Service: kube-dns  (ClusterIP, e.g. 10.96.0.10)        │   │
│   └────────────────────────────────┬────────────────────────┘   │
└────────────────────────────────────┼────────────────────────────┘
                                      │
             every Pod's /etc/resolv.conf:
             nameserver 10.96.0.10
             search default.svc.cluster.local svc.cluster.local cluster.local
                                      │
                                      ▼
              Pod queries: my-svc.default.svc.cluster.local
                                      │
                     ┌────────────────┴────────────────┐
                     ▼                                 ▼
        Normal Service (has ClusterIP)         Headless Service (clusterIP: None)
        → A/AAAA record → the ClusterIP        → A/AAAA records → ALL backing Pod IPs
                                                  (one record per ready Pod)
```

- **CoreDNS has no static configuration to keep in sync** — it is driven directly off live Kubernetes API state via its `kubernetes` plugin, so a new Service is resolvable within moments of creation, with no separate DNS-record management step required.
- **The `search` domains in `/etc/resolv.conf` are what let short names resolve** — a Pod in the `default` namespace querying just `my-svc` works because the resolver automatically appends `default.svc.cluster.local` (and the other search domains in order) until one resolves.
- **Headless Services skip the ClusterIP layer entirely**, making DNS itself the load-balancing/discovery mechanism — clients get back every backing Pod IP directly and choose (or the client library round-robins) among them, rather than relying on kube-proxy ([§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md)) to pick one.

## 5. Hands-On: Working With Cluster DNS

### 5.1 Resolving a Service Name From Inside a Pod

**Purpose:** Confirm basic in-cluster DNS resolution is working and understand the exact naming pattern.

**Syntax:**

```bash
kubectl run -it --rm dnsutils --image=registry.k8s.io/e2e-test-images/jessie-dnsutils:1.3 --restart=Never -- nslookup <service>.<namespace>.svc.cluster.local
```

**Example usage and expected output:**

```bash
$ kubectl run -it --rm dnsutils --image=registry.k8s.io/e2e-test-images/jessie-dnsutils:1.3 --restart=Never -- nslookup web-app.default.svc.cluster.local
Server:    10.96.0.10
Address:   10.96.0.10#53

Name:      web-app.default.svc.cluster.local
Address:   10.96.100.5
```

**Production usage example:** This is the standard first command run when diagnosing "my app can't reach this other Service" — confirming DNS resolves to the expected ClusterIP isolates the problem to either (a) below DNS, in kube-proxy/CNI routing, or (b) an application-level connection issue, before any deeper investigation ([§56](./Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)).

**Common errors:** `nslookup` returning `NXDOMAIN` or timing out entirely (rather than resolving to a wrong IP) almost always points to CoreDNS itself being unhealthy or unreachable, or the queried name being wrong (wrong namespace, typo) — not a routing problem further down the stack.

### 5.2 Understanding the Full DNS Naming Pattern and Record Types

**Purpose:** Know exactly what name resolves to what, including SRV records for named ports, which is frequently tested exam knowledge.

**Syntax:**

```text
<service>.<namespace>.svc.cluster.local          → A/AAAA record (Service ClusterIP, or all Pod IPs if headless)
<pod-ip-dashed>.<namespace>.pod.cluster.local     → A/AAAA record for a Pod directly (rarely used)
_<port-name>._<protocol>.<service>.<namespace>.svc.cluster.local  → SRV record (named port lookup)
```

**Example usage and expected output:**

```bash
$ kubectl run -it --rm dnsutils --image=registry.k8s.io/e2e-test-images/jessie-dnsutils:1.3 --restart=Never -- \
  nslookup -type=SRV _http._tcp.web-app.default.svc.cluster.local
Server:    10.96.0.10
Address:   10.96.0.10#53

_http._tcp.web-app.default.svc.cluster.local  service = 10 33 8080 web-app.default.svc.cluster.local.
```

**Production usage example:** SRV records are used by service-mesh sidecars and some legacy discovery clients that need to discover a named port dynamically rather than assuming a fixed port number — a real, if less common, consumption pattern worth recognizing rather than dismissing SRV records as purely theoretical.

**Common errors:** Confusing the `svc.cluster.local` suffix (the cluster's actual DNS domain, configurable at bootstrap time but almost always left at this default) with a literal, universal constant — clusters that customized this at install time (rare, but possible) need the customized suffix in every fully-qualified lookup.

### 5.3 Headless Service DNS Behavior for StatefulSet Pods

**Purpose:** Demonstrate how a headless Service (`clusterIP: None`) resolves to individual Pod IPs directly — the mechanism StatefulSets ([§33](../Part5/Section-33-Part5-Statefulsets-Stable-Network-Identity-Ordered-Deployment.md)) depend on for stable network identity.

**Syntax:**

```bash
kubectl exec -it <pod> -- nslookup <statefulset-pod-name>.<headless-service>.<namespace>.svc.cluster.local
```

**Example usage and expected output:**

```bash
$ kubectl exec -it client-pod -- nslookup web-0.web-headless.default.svc.cluster.local
Server:    10.96.0.10
Address:   10.96.0.10#53

Name:      web-0.web-headless.default.svc.cluster.local
Address:   10.244.1.12

$ kubectl exec -it client-pod -- nslookup web-headless.default.svc.cluster.local
Server:    10.96.0.10
Address:   10.96.0.10#53

Name:      web-headless.default.svc.cluster.local
Address:   10.244.1.12
Address:   10.244.2.8
Address:   10.244.3.4
```

**Production usage example:** This exact DNS pattern — `<pod-name>.<headless-svc>.<namespace>.svc.cluster.local` resolving to one specific StatefulSet Pod — is how clustered stateful applications (databases, Kafka brokers, Elasticsearch nodes) discover and address specific peers by stable identity rather than through a load-balanced virtual IP, which would defeat the purpose of per-replica addressability.

**Common errors:** Expecting a headless Service's bare name to resolve to a single stable IP the way a normal ClusterIP Service does — it instead returns every backing Pod's IP, requiring the client (or its library) to handle multiple A records correctly.

## 6. Production Usage Notes

- **CoreDNS itself runs as ordinary Pods and can fail like any other workload** — insufficient CPU/memory limits, node pressure, or an accidental low replica count (a single-replica CoreDNS Deployment is a real, seen-in-practice availability risk) can cause cluster-wide, intermittent DNS failures that look like sporadic application errors rather than an obvious outage.
- **DNS caching behavior (Pod-level `dnsConfig`, `ndots` setting) has real performance implications** — Kubernetes' default `ndots:5` setting causes many unnecessary DNS lookups for external (non-cluster) domains, since the resolver tries every search-domain suffix before falling back to treating the name as fully qualified; this is a well-known source of both latency and unnecessary DNS server load in high-QPS applications, sometimes addressed by explicitly setting `dnsConfig.options` per Pod.
- **CoreDNS is configured via the `Corefile` ConfigMap** (`kube-system/coredns`), which platform teams customize for upstream forwarders, custom zone stub domains, or caching TTL tuning — a legitimate, common cluster-level customization point beyond the defaults.

## 7. Security Considerations

- CoreDNS resolves and exposes Service names cluster-wide by default, including across namespaces — this means Service existence and naming conventions are discoverable by any Pod, a factor relevant when NetworkPolicies ([§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) are used to prevent unwanted access, since DNS visibility alone doesn't imply reachability but does imply information disclosure.
- The `kube-dns`/CoreDNS Service and its RBAC permissions (it needs API server read access to Services/Endpoints/Pods) are a sensitive cluster component — compromising CoreDNS or tampering with its `Corefile` could enable DNS spoofing/redirection attacks against in-cluster traffic.

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                                                                                                                                                                 | Resolution Path                                                                                                                                                |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `nslookup`/`dig` for a Service name times out entirely            | CoreDNS Pods unhealthy, crash-looping, or unreachable                                                                                                                                                        | `kubectl get pods -n kube-system -l k8s-app=kube-dns`; check CoreDNS logs and resource limits                                                                  |
| Service resolves to an IP, but connections still fail             | DNS is fine; the issue is below DNS (kube-proxy [§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md) or CNI [§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md) routing) | Move to `curl`/`telnet` against the resolved IP directly to isolate DNS from routing ([§56](./Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)) |
| Headless Service bare name doesn't behave like a normal ClusterIP | Misunderstanding: headless Services intentionally return all Pod IPs, not one                                                                                                                                | Confirm expected behavior; client code must handle multiple A records, or use the `<pod>.<svc>` per-Pod DNS name                                               |
| High/unexpected DNS query volume or latency for external domains  | Default `ndots:5` causing repeated search-domain lookup attempts                                                                                                                                             | Consider per-Pod `dnsConfig` tuning or `dnsPolicy` adjustments for high-QPS workloads calling external services                                                |

## 9. Best Practices

- Run CoreDNS with more than one replica and appropriate resource requests/limits, and monitor it like any other critical cluster-wide dependency — it is a single point of failure for name-based service discovery if under-provisioned.
- Use the fully-qualified `<service>.<namespace>.svc.cluster.local` form in cross-namespace references and in documentation/manifests where clarity matters, even though shorter forms resolve correctly within the same namespace.
- Understand and, where genuinely impactful, tune `ndots`/`dnsConfig` for latency-sensitive workloads that make frequent external DNS calls, rather than accepting default search-domain overhead unexamined.

## 10. Common Anti-Patterns / Mistakes

- **Treating every "Service unreachable" symptom as a DNS problem or a routing problem interchangeably**, without first isolating which layer is actually failing via a direct IP-based test versus a name-based test.
- **Running CoreDNS at a single replica in a production cluster**, creating an avoidable single point of failure for all in-cluster name resolution.
- **Misunderstanding headless Service DNS as "broken" because it returns multiple A records** instead of recognizing this as the intended, correct behavior that StatefulSets and clustered applications rely on.

## 11. Interview Questions

**🎯 Beginner:** _"What is CoreDNS, and what problem does it solve in Kubernetes?"_
**Model answer:** CoreDNS is the default in-cluster DNS server that lets Pods resolve Service names (like `my-service.default.svc.cluster.local`) to the Service's ClusterIP, instead of applications needing to hardcode IP addresses. It runs as a Deployment, watches the API server for live Service/Pod state, and serves DNS records dynamically, so new Services become resolvable almost immediately without any manual DNS record management.
_What the interviewer is probing for:_ Basic understanding that DNS is what makes Services usable by name, and that CoreDNS is dynamically driven off cluster state rather than statically configured.

**🎯 Intermediate:** _"Explain the difference in DNS behavior between a normal Service and a headless Service."_
**Model answer:** A normal Service has a ClusterIP, and its DNS name resolves to that single, stable virtual IP — kube-proxy then load-balances traffic sent to that IP across the backing Pods. A headless Service is created with `clusterIP: None`, which tells Kubernetes not to allocate a virtual IP at all; its DNS name instead resolves directly to the IP addresses of every currently-ready backing Pod, returned as multiple A records. This is the mechanism StatefulSets rely on, since it also enables a further per-Pod DNS name (`<pod-name>.<headless-svc>.<namespace>.svc.cluster.local`) that resolves to one specific Pod's IP, giving each replica a stable, individually addressable identity that a normal load-balanced ClusterIP couldn't provide.
_What the interviewer is probing for:_ Precise understanding of headless Service DNS mechanics, not just that "it's used with StatefulSets."

**🎯 Senior:** _"An application team reports intermittent failures reaching an internal Service, but only during high-traffic periods. How would you determine whether this is a DNS issue?"_
**Model answer:** I'd first isolate DNS from routing by testing both independently under similar load conditions — resolving the Service name repeatedly with `dig`/`nslookup` to check for timeouts or inconsistent answers, separately from testing direct connectivity to the already-resolved ClusterIP with `curl`/`telnet`. If DNS resolution itself is timing out or slow under load, I'd check CoreDNS Pod resource utilization and replica count, since CoreDNS Pods hitting CPU throttling or being under-replicated during traffic spikes is a common, specific cause of exactly this intermittent pattern — as opposed to a genuinely routing- or backend-capacity-related issue, which would show consistent DNS resolution but inconsistent connection success. I'd also check whether the calling application's `ndots` configuration is causing excessive redundant lookups that compound under load, since that amplifies any underlying CoreDNS capacity issue.
_What the interviewer is probing for:_ A structured approach to separating DNS-layer symptoms from routing/backend symptoms, and awareness that CoreDNS itself is a workload subject to resource pressure.

**🎯 Architect:** _"You're designing DNS architecture for a platform hosting hundreds of namespaces with strict multi-tenant isolation requirements. What DNS-related considerations matter at that scale?"_
**Model answer:** Since CoreDNS resolves Service names cluster-wide by default, I'd treat DNS-based Service name/existence visibility as an information-disclosure concern distinct from actual network reachability — mitigated primarily through NetworkPolicies ([§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) rather than trying to restrict DNS visibility itself, since Kubernetes DNS isn't designed to be a tenant isolation boundary. I'd scale CoreDNS replicas and resource allocation proportionally to the platform's total Service/Pod count and query volume, since a single shared CoreDNS deployment is now a shared dependency across every tenant namespace — a CoreDNS capacity or availability incident becomes a platform-wide incident, not a per-tenant one. I'd also standardize `ndots`/`dnsConfig` guidance for tenant workloads making heavy external DNS calls, to prevent one noisy tenant's DNS query pattern from degrading shared CoreDNS capacity for everyone else — treating CoreDNS capacity planning as a first-class multi-tenant platform concern, not an afterthought.
_What the interviewer is probing for:_ Recognition that DNS is a shared, potentially noisy-neighbor-prone dependency at multi-tenant scale, and that isolation for DNS visibility versus actual traffic control require different mechanisms.

## 12. Common Misconceptions

1. **"DNS records in Kubernetes are statically configured, like a traditional DNS zone file."** CoreDNS serves records dynamically off live API server state via its `kubernetes` plugin — there is no static zone file to maintain for in-cluster Services.
2. **"A headless Service's DNS behavior returning multiple IPs is a bug or misconfiguration."** It is the intended, designed behavior, specifically enabling StatefulSet per-Pod addressability.
3. **"DNS resolution failing and a Service being unreachable are always the same problem."** They are distinct layers — DNS resolution can succeed while routing (kube-proxy/CNI) still fails, and vice versa; correct troubleshooting isolates which layer is actually failing.
4. **"The `svc.cluster.local` suffix is a hardcoded, unchangeable constant."** It is the cluster's configured DNS domain, set at bootstrap time and only very rarely customized away from this default.

## 13. 🔑 Key Takeaways

- CoreDNS is the default in-cluster DNS server, dynamically serving records off live API server state — no static DNS zone management required.
- The naming pattern `<service>.<namespace>.svc.cluster.local` resolves to a Service's ClusterIP; SRV records support named-port lookups.
- Headless Services (`clusterIP: None`) resolve to all backing Pod IPs directly rather than one virtual IP, and additionally support stable per-Pod DNS names — the mechanism underlying StatefulSet network identity.
- DNS and routing (kube-proxy, CNI) are distinct troubleshooting layers; isolating which one is failing (name resolution vs. connectivity to the resolved IP) is the correct first triage step.
- CoreDNS is itself an ordinary, resource-constrained workload and a cluster-wide single point of failure if under-replicated or under-provisioned.

## 14. Related Concepts & What's Next

[§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) covers the Service abstraction whose ClusterIPs this section's DNS records resolve to, and [§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md) covers the kube-proxy mechanism that actually routes traffic once DNS has resolved a name to an IP. [§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) returns to headless-Service-adjacent security considerations around DNS visibility as part of NetworkPolicy design, and [§56](./Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md) folds `dig`/`nslookup` into the full in-cluster network troubleshooting toolkit this section's hands-on commands previewed.

**Next Section:** [§53](./Section-53-Part7-Ingress-Ingress-Controllers.md) — `Section-53-Part7-Ingress-Ingress-Controllers.md`
