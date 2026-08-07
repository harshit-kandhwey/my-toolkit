# Section 49 (Part 7): CNI Plugins Compared: Calico, Flannel, Cilium, Weave

## 1. Definition

**Plain language:** [§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md) established that Kubernetes requires every Pod to have its own routable IP and to reach every other Pod without NAT — but Kubernetes itself doesn't build the roads that make that happen. A CNI plugin is the actual road-builder, and different plugins build fundamentally different kinds of roads: some dig tunnels (overlays), some publish real routes to the network (BGP), and some bypass traditional routing almost entirely by programming the kernel directly (eBPF).

**Precise definition:** A **CNI (Container Network Interface) plugin** is the pluggable component, installed at cluster bootstrap time ([§23](../Part3/Section-23-Part3-Cluster-Networking-Prerequisites-CNI-Plugin-Selection.md)), that implements the actual Pod networking data plane — allocating Pod IPs from the cluster's Pod CIDR and establishing the routing/forwarding mechanism that fulfills the flat-network contract from [§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md). **Flannel** implements this primarily via a simple **overlay network** (VXLAN encapsulation by default). **Calico** implements it primarily via **native BGP route advertisement** (with an optional VXLAN/IP-in-IP overlay fallback for networks where BGP peering isn't feasible) and additionally provides its own robust NetworkPolicy enforcement engine. **Cilium** implements it via an **eBPF-based datapath**, bypassing much of the traditional iptables/netfilter stack entirely for both packet forwarding and NetworkPolicy enforcement, while also offering Layer 7-aware policy and observability (Hubble). **Weave (Weave Net)** implements it via its own **mesh overlay** with automatic peer discovery, historically valued for simplicity in smaller or ad hoc clusters.

## 2. Why This Matters

- **The plugin you choose determines whether NetworkPolicy ([§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) even works, and how well.** Flannel alone provides no NetworkPolicy enforcement at all (it is commonly paired with Calico's policy engine in a "Canal" combination for exactly this reason); Calico and Cilium both enforce NetworkPolicy natively, but through very different mechanisms with different performance and feature ceilings (Cilium supports Layer 7 policy; Calico's native policy is Layer 3/4 plus an extended CRD-based policy model).
- **This is a direct continuation of the install-time decision made in [§23](../Part3/Section-23-Part3-Cluster-Networking-Prerequisites-CNI-Plugin-Selection.md)** — CNI plugin selection isn't something reconsidered casually after a cluster is running; migrating CNI plugins on a live cluster is disruptive and rarely done, making this one of the highest-consequence early architectural decisions in a cluster's life.
- **Performance and observability characteristics genuinely differ, not just marketing claims.** An eBPF datapath (Cilium) avoids iptables rule-chain traversal overhead that scales poorly with very large numbers of Services/Pods, which is a real, measurable difference at scale — relevant to the multi-cluster/enterprise-scale considerations in Part 16.

🔑 **Key Takeaway:** All four plugins satisfy the same flat-network contract from [§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md), but they satisfy it through genuinely different mechanisms — overlay tunneling (Flannel, Weave), BGP route advertisement (Calico), or an eBPF datapath (Cilium) — and those mechanism differences directly determine NetworkPolicy capability, performance at scale, and encryption support, making the choice a substantive architectural decision, not an interchangeable default.

## 3. Prerequisites and Dependencies

Builds directly on [§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md) (the flat-network contract these plugins implement) and [§23](../Part3/Section-23-Part3-Cluster-Networking-Prerequisites-CNI-Plugin-Selection.md) (CNI plugin selection as a cluster-bootstrap prerequisite).

## 4. Architecture Diagram

```text
     Flannel (overlay/VXLAN)
     ┌─────────────────────┐         ┌─────────────────────┐
     │       Node A        │──VXLAN─►│       Node B        │
     │ Pod IP encapsulated │  tunnel │ Pod IP decapsulated │
     └─────────────────────┘         └─────────────────────┘
                    No native Network Policy
     (often paired with Calico's policy engine as "Canal")



     Calico (BGP, overlay fallback)
     ┌──────────────────────┐          ┌──────────────────────┐
     │       Node A         │◄──BGP──► │       Node B         │
     │ Pod IP routes        │ peering  │ Pod IP routes        │
     │ advertised natively  │          │                      │
     └──────────────────────┘          └──────────────────────┘
               Kubernetes Native Network Policy
     (Layer 3/4 + Calico-specific GlobalNetworkPolicy CRDs)
                    (enforced by Felix)



     Cilium (eBPF datapath)
     ┌──────────────────────┐          ┌──────────────────────┐
     │       Node A         │◄────────►│       Node B         │
     │ eBPF programs        │ Direct   │ eBPF programs        │
     │ in kernel            │ Routing/ │                      │
     │ bypass iptables      │ VXLAN    │                      │
     └──────────────────────┘          └──────────────────────┘
     Kubernetes NetworkPolicy + L7-aware policy + Hubble observability



     Weave (mesh overlay)
     ┌──────────────────────┐          ┌──────────────────────┐
     │       Node A         │◄──mesh──►│       Node B         │
     │ Pod IP overlay       │ overlay  │ Pod IP overlay       │
     └──────────────────────┘          └──────────────────────┘
               └── with automatic peer discovery ──┘
     No native NetworkPolicy in original Weave Net (policy
     addons vary by distribution)


```

- **Overlay-based plugins (Flannel, Weave) encapsulate Pod traffic inside another protocol** (typically VXLAN or a custom mesh protocol) for the cross-node hop, adding some encapsulation overhead but requiring minimal underlying network cooperation — they work even on networks where the underlying infrastructure has no awareness of Pod CIDRs at all.
- **Calico's BGP mode advertises Pod routes directly into the network's routing table**, avoiding encapsulation overhead entirely, but requires either a network that supports BGP peering or falls back to an IP-in-IP/VXLAN overlay when direct peering isn't feasible (e.g., most public cloud VPCs).
- **Cilium's eBPF datapath operates at the kernel level**, programmed dynamically, and can replace not just Pod routing but also large parts of kube-proxy's traditional iptables/IPVS-based Service routing ([§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md)) — a materially different architectural approach from the other three.

## 5. Hands-On: Identifying and Inspecting the Installed CNI Plugin

### 5.1 Identifying Which CNI Plugin a Cluster Is Running

**Purpose:** Determine the installed CNI plugin on an unfamiliar cluster before doing any networking troubleshooting.

**Syntax:**

```bash
kubectl get pods -n kube-system -o wide | grep -Ei 'calico|flannel|cilium|weave'
```

**Example usage and expected output:**

```bash
$ kubectl get pods -n kube-system -o wide | grep -Ei 'calico|flannel|cilium|weave'
calico-node-4x2vp         1/1     Running   worker-1
calico-node-8k9zt         1/1     Running   worker-2
calico-kube-controllers-6f7d9   1/1   Running   control-1
```

**Production usage example:** This is typically the very first command run when inheriting or debugging an unfamiliar cluster — it immediately tells an SRE which mechanism (BGP, overlay, eBPF) is in play, which then determines the entire rest of the network-troubleshooting approach ([§56](./Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)).

**Common errors:** Some managed offerings (EKS's default VPC CNI, GKE's default) don't surface as an obviously-named `kube-system` Pod set in the same way — check the cloud provider's own documentation/console for cluster networking mode when this grep comes up empty.

### 5.2 Inspecting Calico's BGP Peering Status

**Purpose:** Verify that Calico's BGP-based route advertisement is actually healthy between nodes — the mechanism that makes cross-node Pod routing work without an overlay.

**Syntax:**

```bash
kubectl exec -n kube-system calico-node-4x2vp -- calicoctl node status
```

**Example usage and expected output:**

```bash
$ kubectl exec -n kube-system calico-node-4x2vp -- calicoctl node status
Calico process is running.

IPv4 BGP status
+--------------+-------------------+-------+----------+-------------+
| PEER ADDRESS | PEER TYPE         | STATE | SINCE    | INFO        |
+--------------+-------------------+-------+----------+-------------+
| 10.0.1.11    | node-to-node mesh | up    | 03:14:22 | Established |
+--------------+-------------------+-------+----------+-------------+
```

**Production usage example:** When cross-node Pod-to-Pod connectivity fails (the exact symptom troubleshot in [§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md)), an operator running Calico checks this output first — a peer showing anything other than `up`/`Established` directly explains why routes to that node's Pods aren't being learned, isolating the problem to BGP peering specifically rather than a broader network fault.

### 5.3 Inspecting Cilium's eBPF-Based Connectivity Status

**Purpose:** Verify Cilium's own view of cluster connectivity health, since traditional iptables-focused tools give an incomplete picture of an eBPF datapath.

**Syntax:**

```bash
kubectl exec -n kube-system ds/cilium -- cilium status --brief
```

**Example usage and expected output:**

```bash
$ kubectl exec -n kube-system ds/cilium -- cilium status --brief
OK   Cilium: OK, 3 nodes online, all healthy
     Controllers: 24/24 healthy
     Cluster health: 3/3 reachable
```

**Production usage example:** Because Cilium replaces much of the traditional iptables path, standard `iptables -L` inspection often shows little useful information for Pod networking issues on a Cilium cluster — `cilium status` and the companion Hubble observability tooling (`hubble observe`) are the correct diagnostic entry points instead, a distinction worth knowing before wasting time on the wrong tool for the platform.

**Common errors:** Running traditional `iptables`-focused troubleshooting steps (written with Flannel/Calico's iptables-based dataplane in mind) against a Cilium eBPF cluster often shows nothing meaningful, misleading an operator into thinking there's no relevant rule state at all — the state exists, just enforced via eBPF programs rather than iptables chains.

## 6. Production Usage Notes

- **Flannel is frequently chosen for simplicity in smaller, single-cloud, single-purpose clusters** where NetworkPolicy enforcement isn't a hard requirement, or is delegated to a paired policy engine (the "Canal" combination of Flannel's networking plus Calico's policy engine).
- **Calico is a common default in enterprise and CKS-relevant environments** precisely because of its mature, native NetworkPolicy engine and its ability to run without an overlay (lower latency, no encapsulation overhead) when the underlying network supports BGP peering — public cloud environments often still require its overlay fallback since most VPCs don't support direct BGP peering with Pod-level granularity.
- **Cilium's eBPF approach shows measurable performance advantages at very high Service/Pod counts**, since it avoids the linear iptables rule-chain traversal that becomes a real bottleneck in traditional kube-proxy/iptables setups at scale ([§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md)) — a genuine reason large-scale platforms increasingly adopt it, not just its additional Layer 7 policy and observability features.
- **Weave's simplicity and automatic peer discovery made it historically popular for quick local/on-prem setups**, but it has seen comparatively less enterprise-scale investment and feature growth (native Layer 7 policy, eBPF-level performance) relative to Calico and Cilium in recent years — a real factor to weigh for new, long-lived cluster builds.

## 7. Security Considerations

- **Only Calico and Cilium provide mature, native NetworkPolicy enforcement out of the box** — a cluster running plain Flannel or original Weave Net without a paired policy engine effectively has no way to enforce the default-deny NetworkPolicy posture covered in [§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md), a real gap that must be identified and addressed at CNI selection time, not discovered later during a security review.
- **Some plugins support encrypting Pod-to-Pod traffic at the CNI layer itself** (Calico with WireGuard-backed encryption, Cilium with IPsec or WireGuard) — a meaningful capability for satisfying "encrypt data in transit" requirements without needing a full service mesh ([§122](../Part16/Section-122-Part16-Service-Mesh-Concepts-Sidecar-Proxy-Pattern.md)), and a factor directly relevant to the CKS network-security domain ([§121](../Part15/Section-121-Part15-Monitoring-Logging-Runtime-Threat-Detection-CKS-Exam.md)).
- **eBPF-based plugins (Cilium) run privileged kernel-level code by design** — this is a legitimate, necessary part of how the plugin works, but it also means the CNI's own security posture (image provenance, kernel version compatibility, RBAC around who can modify Cilium's own resources) deserves the same hardening scrutiny as any other cluster-critical, highly privileged component.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                  | Resolution Path                                                                                                                                  |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| NetworkPolicy manifest applied but traffic still isn't restricted      | Running Flannel (or Weave without a policy engine) with no native enforcement | Confirm the CNI plugin actually supports NetworkPolicy; pair with Calico's engine or migrate                                                     |
| Cross-node Pod traffic fails intermittently on a Calico cluster        | BGP peering between specific nodes is down or flapping                        | Run `calicoctl node status` on affected nodes; check underlying network/firewall for BGP traffic                                                 |
| Traditional `iptables -L` shows no relevant rules on a Cilium cluster  | Cilium's eBPF datapath doesn't rely on iptables the way other plugins do      | Use `cilium status` and `hubble observe` instead of iptables-based inspection                                                                    |
| Overlay-based cluster (Flannel/Weave) shows added latency vs. expected | VXLAN/mesh encapsulation overhead on every cross-node packet                  | Confirm whether overlay is actually required (BGP-capable network may allow Calico's non-overlay mode) or evaluate an eBPF-based plugin at scale |

## 9. Best Practices

- Choose a CNI plugin based on concrete requirements (NetworkPolicy maturity, encryption needs, expected scale, Layer 7 policy needs) rather than defaulting to whichever plugin a tutorial happened to use.
- Document which CNI plugin a cluster runs and its specific mechanism (overlay/BGP/eBPF) prominently in cluster runbooks, since the correct troubleshooting toolchain differs materially between them.
- Re-evaluate CNI choice deliberately at major cluster rebuilds rather than never revisiting it, since plugin capabilities (especially Cilium's) have evolved substantially and an earlier constraint may no longer apply.

## 10. Common Anti-Patterns / Mistakes

- **Assuming any CNI plugin automatically enforces NetworkPolicy**, then discovering during a security audit that Flannel alone was providing no policy enforcement at all.
- **Applying iptables-centric troubleshooting habits unchanged to an eBPF-based (Cilium) cluster**, missing that the correct tools and mental model are different.
- **Treating CNI plugin choice as a low-stakes default rather than a deliberate architectural decision**, then facing a disruptive migration later once NetworkPolicy, encryption, or scale requirements outgrow the original plugin's capabilities.

## 11. Interview Questions

**🎯 Beginner:** _"Name two ways different CNI plugins actually implement Pod-to-Pod networking."_
**Model answer:** Overlay networking (Flannel, Weave), where Pod traffic is encapsulated in a tunneling protocol like VXLAN for the cross-node hop, and native BGP route advertisement (Calico), where Pod routes are published directly into the network's routing tables without encapsulation. A third, more modern approach is an eBPF-based datapath (Cilium), which programs the Linux kernel directly rather than relying on either an overlay or traditional iptables rules.
_What the interviewer is probing for:_ Basic awareness that "CNI plugin" isn't a single implementation pattern — different plugins solve the same contract differently.

**🎯 Intermediate:** _"Why might a team running Flannel also deploy Calico in the same cluster?"_
**Model answer:** This is the "Canal" pattern — Flannel handles the actual Pod networking (typically via VXLAN overlay), while Calico is deployed specifically for its mature NetworkPolicy enforcement engine, since Flannel alone provides no native NetworkPolicy capability. It lets a team keep Flannel's simple networking while gaining real policy enforcement, rather than migrating the entire networking layer to Calico just to get policy support.
_What the interviewer is probing for:_ Understanding that CNI "plugin" can actually be a combination of components solving different parts of the networking contract, and specifically why NetworkPolicy support isn't universal across plugins.

**🎯 Senior:** _"A platform team is seeing kube-proxy/iptables rule processing become a measurable latency bottleneck as Service count grows past several thousand. What CNI-related option would you evaluate, and why?"_
**Model answer:** I'd evaluate migrating to Cilium's eBPF-based datapath, which can replace much of kube-proxy's traditional iptables-based Service routing ([§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md)) with eBPF programs that don't suffer the same linear rule-chain traversal cost as iptables does at scale — a well-documented, measurable improvement at high Service/Pod counts. I'd caveat that this is a genuinely disruptive migration (not a config toggle), requiring careful validation of existing NetworkPolicies' behavior under Cilium's policy engine, confirming kernel version compatibility across all nodes for the required eBPF features, and planning a careful cutover rather than treating it as a drop-in replacement — the performance case is real, but the migration cost needs to be weighed against it explicitly.
_What the interviewer is probing for:_ Whether the candidate connects a real operational symptom (iptables scaling limits) to a specific, technically accurate CNI-level solution, while still recognizing migration isn't free.

**🎯 Architect:** _"You're building a Kubernetes platform for a regulated industry requiring encrypted pod-to-pod traffic and strong, auditable network policy enforcement, deployed across both on-prem bare metal and a public cloud. How does CNI plugin choice factor into satisfying these requirements across both environments?"_
**Model answer:** I'd lean toward Calico or Cilium specifically because both provide native NetworkPolicy enforcement with a mature policy CRD model suitable for audit requirements, and both support CNI-layer encryption (Calico via WireGuard, Cilium via WireGuard or IPsec) which can satisfy encrypted-pod-traffic requirements without necessarily requiring a full service mesh's mTLS overhead. For the bare-metal environment, Calico's native BGP mode would avoid overlay overhead if the underlying network supports peering; for the public cloud environment, I'd expect to fall back to Calico's overlay mode (since most cloud VPCs don't support direct Pod-level BGP peering) or evaluate whether the cloud's own CNI integration plus Cilium's policy/encryption layer meets the requirement instead. The key architectural point for a regulated, multi-environment platform is standardizing on one CNI plugin's policy and encryption model across both environments where possible, since running genuinely different CNI plugins per environment would mean maintaining two separate policy authoring and audit models for what should be one consistent security posture.
_What the interviewer is probing for:_ Ability to map concrete regulated-industry requirements (encryption, auditable policy) onto specific, real CNI plugin capabilities, and to reason about consistency across heterogeneous environments rather than treating each environment's CNI choice in isolation.

## 12. Common Misconceptions

1. **"All CNI plugins provide NetworkPolicy enforcement."** Flannel and original Weave Net do not natively enforce NetworkPolicy; only Calico and Cilium (among these four) provide mature native enforcement.
2. **"Overlay networking and BGP-based routing perform identically."** Overlay encapsulation (VXLAN) adds real per-packet overhead that BGP-advertised native routing avoids — a genuine, measurable performance difference, not just a theoretical one.
3. **"Cilium is just Calico with extra features."** Cilium's eBPF-based datapath is architecturally distinct from Calico's iptables/BGP-based approach — it's a different implementation strategy, not an incremental feature addition on the same foundation.
4. **"Changing CNI plugins is a simple configuration change."** Migrating a live cluster's CNI plugin is one of the more disruptive operations possible, typically requiring careful planning, workload migration, or a cluster rebuild rather than an in-place swap.

## 13. 🔑 Key Takeaways

- Flannel implements Pod networking primarily via VXLAN overlay and provides no native NetworkPolicy enforcement on its own.
- Calico implements Pod networking primarily via native BGP route advertisement (with overlay fallback) and provides a mature native NetworkPolicy engine.
- Cilium implements Pod networking and Service routing via an eBPF datapath, offering both native NetworkPolicy (including Layer 7-aware policy) and measurable performance advantages at scale.
- Weave provides a simple mesh overlay with automatic peer discovery, historically valued for small/ad hoc setups but with less recent enterprise-scale feature investment than Calico or Cilium.
- CNI plugin choice directly determines NetworkPolicy capability, encryption support, and performance characteristics — it is a substantive architectural decision made at cluster bootstrap ([§23](../Part3/Section-23-Part3-Cluster-Networking-Prerequisites-CNI-Plugin-Selection.md)), not an interchangeable default.

## 14. Related Concepts & What's Next

[§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md) established the flat-network contract every plugin covered here fulfills, and [§23](../Part3/Section-23-Part3-Cluster-Networking-Prerequisites-CNI-Plugin-Selection.md) covered CNI selection as an install-time prerequisite. [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) moves up a layer to Services, which are built entirely on top of whichever Pod network foundation this section's plugins provide, and [§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) (NetworkPolicy) returns to the enforcement-capability gap noted here with full rule-design depth.

**Next Section:** [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) — `Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md`
