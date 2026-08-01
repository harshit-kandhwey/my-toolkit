# Section 48 (Part 7): Kubernetes Networking Model: the Flat Network and Pod-to-Pod Communication Rules

## 1. Definition

**Plain language:** In most networking you've dealt with, machines behind NAT can't directly reach each other without port-forwarding tricks. Kubernetes deliberately rejects that model for Pods: every Pod gets its own real IP address, and any Pod can talk to any other Pod's IP directly, on any port, from any node, with no NAT and no translation in between — full stop.

**Precise definition:** The **Kubernetes networking model** mandates that every Pod receives a unique, cluster-routable IP address (from the **Pod CIDR**), and requires that this "flat network" property hold cluster-wide: **Pods can communicate with all other Pods on any node without NAT**, **Pods on a node can communicate with all Pods on all nodes without NAT**, and **the IP a Pod sees itself as is the same IP everyone else sees it as** (no address translation between the Pod's own view and the outside view). Kubernetes itself does not implement this — it is a _contract_ that a **CNI (Container Network Interface) plugin**, covered at install-time-prerequisite level in §23 and compared in depth in §49, is responsible for actually fulfilling.

## 2. Why This Matters

- **This model is what makes Kubernetes networking simpler to reason about than it initially sounds.** Because there's no NAT between Pods, `curl http://<pod-ip>:8080` behaves identically regardless of which node either Pod is running on — a property so foundational that almost every higher-level abstraction (Services in §50, DNS in §52, NetworkPolicy in §55) is built assuming it already holds.
- **It's a contract enforced by the CNI plugin, not by Kubernetes core** — understanding this separation explains why choosing a CNI plugin (§49) is a real architectural decision with real consequences (performance, feature support, encryption) rather than an interchangeable checkbox, and why CNI plugin selection is a required decision at cluster install time (§23).
- **kube-proxy (§9) builds Service abstraction directly on top of this flat network** — Services work by rewriting a virtual IP into one of the flat, routable Pod IPs backing it; without the flat-network guarantee already in place, Service routing as implemented today wouldn't be possible, which is why this section deliberately comes before §51's kube-proxy mechanics.

🔑 **Key Takeaway:** Kubernetes assumes a flat, NAT-free Pod network as a foundational contract — every Pod gets a real, cluster-routable IP that looks the same from every angle — and every other networking abstraction in Part 7 (Services, DNS, Ingress, NetworkPolicy) is built as a layer on top of this guarantee, not a replacement for it.

## 3. Prerequisites and Dependencies

Builds on §9 (kube-proxy's role as a node component) and §23 (CNI plugin selection as an install-time cluster prerequisite); assumes the basic core-networking baseline (IP addressing, routing) noted in the roadmap's prerequisites.

## 4. Architecture Diagram

```text
                    Node A (10.0.1.10)              Node B (10.0.1.11)
   ┌────────────────────────────────────┐  ┌────────────────────────────────────┐
   │  Pod CIDR slice: 10.244.1.0/24     │  |Pod CIDR slice: 10.244.2.0/24       │
   │                                    │  │                                    │
   │  ┌──────────┐      ┌──────────┐    │  │  ┌──────────┐      ┌──────────┐    │
   │  │ Pod A1   │      │ Pod A2   │    │  │  │ Pod B1   │      │ Pod B2   │    │
   │  │10.244.1.5│      │10.244.1.6│    │  │  │10.244.2.7│      │10.244.2.8│    │
   │  └────┬─────┘      └────┬─────┘    │  │  └────┬─────┘      └────┬─────┘    │
   │       │  no NAT, direct L3 routing │  │       │  no NAT, direct L3 routing │
   └───────┼───────────────┼────────────┘  └───────┼───────────────┼────────────┘
           │               │                       │               │
           └───────────────┴───────── CNI plugin ──┴───────────────┘
                    (overlay tunnel, BGP routes, or eBPF datapath —
                     mechanism varies by plugin, §49)
           Pod A1 (10.244.1.5) ──► Pod B1 (10.244.2.7) directly, no NAT,
           regardless of which physical node either Pod lands on
```

- **Each node is assigned a slice of the cluster-wide Pod CIDR** (e.g., a `/24` per node out of a `/16` cluster range) — this is how Pod IPs stay unique cluster-wide without central IP allocation on every Pod creation.
- **The path between Pod A1 and Pod B1 crosses node boundaries but never involves NAT** — the CNI plugin is responsible for making that cross-node routing actually work, whether via an overlay tunnel, BGP-advertised routes, or an eBPF-programmed datapath (§49 covers each mechanism concretely).
- **kube-proxy and Services sit logically above this diagram**, not inside it — they route to a Pod IP that this flat network then delivers without further translation.

## 5. Hands-On: Observing the Flat Network Directly

### 5.1 Inspecting Pod IPs Across Nodes

**Purpose:** Confirm directly that Pods on different nodes hold distinct, routable IPs from the cluster's Pod CIDR.

**Syntax:**

```bash
kubectl get pods -o wide
```

**Example usage and expected output:**

```bash
$ kubectl get pods -o wide
NAME        READY   STATUS    NODE       IP
web-app-1   1/1     Running   worker-1   10.244.1.5
web-app-2   1/1     Running   worker-2   10.244.2.7
cache-1     1/1     Running   worker-1   10.244.1.9
```

**Production usage example:** When diagnosing a suspected networking issue, confirming that Pods actually have distinct IPs consistent with their node's CIDR slice (versus, say, all showing the same IP due to a misconfigured CNI plugin) is often the very first sanity check before deeper investigation (§101, Part 13).

### 5.2 Verifying Direct Pod-to-Pod Reachability Across Nodes

**Purpose:** Prove the no-NAT, cross-node Pod communication contract directly, rather than trusting it as theory.

**Syntax:**

```bash
kubectl exec -it web-app-1 -- curl -s http://10.244.2.7:8080/healthz
```

**Example usage and expected output:**

```bash
$ kubectl exec -it web-app-1 -- curl -s http://10.244.2.7:8080/healthz
{"status":"ok"}
```

**Production usage example:** This exact command pattern — one Pod curling another Pod's raw IP directly, with no Service in between — is a standard first step in the network-troubleshooting toolkit (§56) to isolate whether a reported networking problem is at the raw Pod-to-Pod layer (a CNI/routing issue) or a Service/DNS layer issue (§50, §52) sitting above it.

**Common errors:** If this direct Pod-IP curl fails while the Pods otherwise report `Running`, the problem is very likely in the CNI plugin's cross-node routing (a misconfigured overlay, a missing BGP peer, a security group blocking the CNI's encapsulation protocol) rather than anything at the Kubernetes object level — check CNI plugin pod logs (typically in `kube-system`) next.

### 5.3 Inspecting the Node's Pod CIDR Allocation

**Purpose:** See the specific Pod CIDR slice a node has been assigned, explaining why that node's Pods all fall in a specific IP range.

**Syntax:**

```bash
kubectl get node worker-1 -o jsonpath='{.spec.podCIDR}'
```

**Example usage and expected output:**

```bash
$ kubectl get node worker-1 -o jsonpath='{.spec.podCIDR}'
10.244.1.0/24
```

**Production usage example:** When planning cluster-wide IP capacity (how many Pods the cluster can ever run simultaneously), platform teams calculate this from the overall cluster Pod CIDR size divided by the per-node slice size — a real, sometimes overlooked capacity constraint distinct from CPU/memory capacity, since running out of allocatable Pod IPs prevents scheduling new Pods even when compute resources remain available.

## 6. Production Usage Notes

- **The Pod CIDR range is chosen at cluster bootstrap time (§16, kubeadm's `--pod-network-cidr`) and is expensive to change later** — undersizing it (too few addresses for the cluster's eventual scale) is a real, hard-to-fix-in-place capacity mistake that should be planned for expected cluster growth, not just current size.
- **"No NAT between Pods" does not mean "no NAT anywhere"** — traffic leaving the cluster to the public internet is still typically SNAT'd through the node's IP (or a NAT gateway in cloud environments); the no-NAT guarantee is specifically a Pod-to-Pod, intra-cluster contract.
- **Cloud-managed Kubernetes (EKS/AKS/GKE) each implement the Pod CIDR/routing differently under the hood** (e.g., EKS's VPC CNI assigning routable VPC IPs directly to Pods versus an overlay-based approach elsewhere) — the flat-network _contract_ is identical, but how it's achieved varies significantly and has real implications for Pod density per node and VPC IP exhaustion (§49, §127 in Part 16).

## 7. Security Considerations

- **The flat, no-NAT network model means that, by default, every Pod can reach every other Pod in the entire cluster** — there is no isolation whatsoever until NetworkPolicy (§55) is explicitly applied; a fresh cluster with no NetworkPolicies is fully open at the Pod-network layer regardless of Namespace boundaries (§47).
- **CNI plugin choice has direct security implications** — some plugins support encrypting Pod-to-Pod traffic at the CNI layer (e.g., WireGuard-backed encryption in Calico) while others do not natively, a factor covered concretely per-plugin in §49 and relevant to CKS's network security domain (§121).

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                                                          | Resolution Path                                                                                  |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Pods on the same node reach each other, but cross-node Pods can't | CNI plugin's cross-node routing/overlay is broken (BGP peering down, overlay interface misconfigured) | Check CNI plugin Pods/logs in `kube-system`; verify overlay/BGP state per plugin (§49)           |
| New Pods stuck `Pending`, cluster otherwise healthy on CPU/memory | Node's Pod CIDR slice exhausted (too many Pods already assigned IPs on that node)                     | Check `kubectl describe node` for IP allocation; consider Pod CIDR sizing or node scaling        |
| Pod-to-Pod curl works by IP but fails by Service name             | Not a flat-network issue at all — points to DNS/Service layer (§50, §52) instead                      | Isolate at the correct layer: confirm this section's Pod-IP reachability first, then Service/DNS |
| All Pods appear to share the same or overlapping IPs              | CNI misconfiguration or two CNI plugins conflicting on the same cluster                               | Ensure only one CNI plugin is installed and correctly configured; check plugin logs              |

## 9. Best Practices

- Size the cluster's Pod CIDR generously at bootstrap time based on expected long-term cluster growth, since resizing it after the fact is disruptive and sometimes requires a cluster rebuild.
- When diagnosing any networking issue, deliberately start at the Pod-to-Pod IP layer (this section) before assuming the problem is in Services, DNS, or Ingress — it's the foundation every higher layer depends on.
- Treat the choice of CNI plugin as an architectural decision requiring real evaluation (§49), not a default accepted without consideration, since it directly determines encryption support, performance characteristics, and NetworkPolicy enforcement capability.

## 10. Common Anti-Patterns / Mistakes

- **Assuming Kubernetes itself implements Pod networking** rather than recognizing it as a contract fulfilled by a pluggable CNI plugin — this misunderstanding leads to looking in the wrong place (Kubernetes core logs) when networking actually breaks (it's almost always the CNI plugin).
- **Deploying a cluster with no NetworkPolicy and assuming Namespace separation provides network isolation** — the flat network model means, absent NetworkPolicy, every Pod can reach every other Pod cluster-wide regardless of Namespace.
- **Undersizing the cluster's Pod CIDR at bootstrap** based only on the cluster's initial size, then hitting a hard IP-exhaustion wall as the cluster grows, requiring painful remediation.

## 11. Interview Questions

**🎯 Beginner:** _"What does it mean that Kubernetes has a 'flat' Pod network?"_
**Model answer:** Every Pod gets its own unique IP address, and any Pod can reach any other Pod's IP directly — on any port, from any node — without any NAT translation happening in between. The IP a Pod sees itself as is the same IP every other Pod sees it as, unlike typical NAT'd networking where an internal and external address might differ.
_What the interviewer is probing for:_ Basic, correct grasp of the no-NAT, unique-IP-per-Pod contract as the foundational networking fact of Kubernetes.

**🎯 Intermediate:** _"Who actually implements the flat-network guarantee — is it Kubernetes itself?"_
**Model answer:** No — Kubernetes defines the networking model as a requirement/contract, but the actual mechanism (how Pod IPs get routed across nodes without NAT) is implemented by a CNI plugin, chosen and installed at cluster bootstrap time. Different plugins (Calico, Flannel, Cilium, Weave) satisfy this contract through very different underlying mechanisms — overlay tunneling, BGP route advertisement, or an eBPF datapath — but from the workload's perspective the guarantee looks identical regardless of which plugin is underneath.
_What the interviewer is probing for:_ Understanding the separation between Kubernetes' networking contract and the CNI plugin's implementation of it, which is essential for correctly troubleshooting networking issues.

**🎯 Senior:** _"A Pod can reach another Pod on the same node but not one on a different node, even though both Pods report `Running`. Walk through your diagnostic approach."_
**Model answer:** Since same-node Pod-to-Pod works but cross-node doesn't, the issue is almost certainly in the CNI plugin's cross-node transport rather than anything at the Kubernetes scheduling or Pod-status level — same-node traffic often traverses a simple local bridge that doesn't exercise the CNI's cross-node mechanism at all. I'd check the CNI plugin's own Pods/logs in `kube-system` for errors, then check the plugin's specific cross-node mechanism: for an overlay-based plugin, whether the overlay interface/tunnel is up on both nodes; for a BGP-based plugin, whether BGP peering between the two nodes is established; for an eBPF-based plugin, whether the eBPF programs are correctly loaded and any relevant node-level firewall or security-group rules aren't blocking the plugin's specific encapsulation protocol or port. I'd also verify at the infrastructure layer whether a security group or firewall rule between the two specific nodes was recently changed, since that's a common cause distinct from the CNI plugin's own configuration.
_What the interviewer is probing for:_ Structured elimination that correctly narrows from "flat network is broken generally" to "specifically the cross-node path," and familiarity with how different CNI implementation mechanisms fail differently.

**🎯 Architect:** _"You're advising a platform team migrating from a single large on-prem cluster to a multi-cloud strategy spanning bare-metal and a managed cloud Kubernetes offering. What does the flat-network model's dependence on the CNI plugin mean for that migration?"_
**Model answer:** Because the flat-network guarantee is a contract, not an implementation, workloads themselves don't need to change — but the CNI plugin very likely does, since bare-metal typically uses an overlay or BGP-based plugin (no underlying cloud VPC to integrate with) while some managed cloud offerings use cloud-native CNI implementations that assign Pods real VPC-routable IPs directly (trading some flexibility for tighter cloud-network integration and different Pod-density-per-node limits driven by the VPC's own subnet sizing). I'd flag that this affects Pod IP capacity planning (VPC subnet sizing versus an internal overlay CIDR), whether NetworkPolicy enforcement is even supported by the target CNI (not all plugins enforce it — a real gap some teams discover only after migrating), and whether any CNI-specific features the current setup relies on (encrypted Pod traffic, specific eBPF-based observability) have an equivalent on the new platform. The core lesson for the team is that "the network model looks the same to your applications" doesn't mean "the CNI migration is a non-event" — it's one of the highest-risk components of a Kubernetes platform migration precisely because it operates below the abstraction level most application teams ever think about.
_What the interviewer is probing for:_ Whether the candidate can reason about the CNI plugin as a genuinely swappable but non-trivial implementation detail, and correctly identifies the concrete operational risks (IP capacity, NetworkPolicy support, feature parity) a CNI migration introduces even when the contract stays constant.

## 12. Common Misconceptions

1. **"Kubernetes itself routes Pod traffic."** Kubernetes defines the flat-network contract; a separately installed CNI plugin is what actually implements the routing mechanism.
2. **"No NAT between Pods means no NAT anywhere in the cluster."** Traffic leaving the cluster to external destinations is commonly still NAT'd at the node or cloud-gateway level; the no-NAT guarantee is specifically intra-cluster, Pod-to-Pod.
3. **"Namespaces provide network isolation on a flat network."** They don't — absent NetworkPolicy, every Pod can reach every other Pod cluster-wide regardless of which Namespace either lives in.
4. **"All CNI plugins implement the flat network the same way."** The contract (unique routable IP, no NAT) is identical across compliant plugins, but the actual mechanism — overlay, BGP, eBPF — differs substantially and has real performance, security, and NetworkPolicy-support consequences (§49).

## 13. 🔑 Key Takeaways

- Kubernetes mandates a flat, NAT-free Pod network: every Pod gets a unique, cluster-routable IP, reachable directly from any other Pod on any node.
- This is a contract Kubernetes defines but does not implement — a CNI plugin, chosen at cluster bootstrap (§23), is responsible for actually fulfilling it.
- Every higher-level networking abstraction covered later in Part 7 — Services (§50), kube-proxy mechanics (§51), DNS (§52), NetworkPolicy (§55) — is built on top of this flat-network guarantee, not a replacement for it.
- Absent explicit NetworkPolicy, the flat network means every Pod can reach every other Pod cluster-wide by default — a security-relevant fact, not just a connectivity one.
- When troubleshooting any networking symptom, verify raw Pod-to-Pod IP reachability first (this section's diagnostic pattern) before assuming the problem is at the Service, DNS, or Ingress layer.

## 14. Related Concepts & What's Next

§9 introduced kube-proxy as a node component; this section establishes the flat-network foundation that kube-proxy's Service routing (§51) is built directly on top of. §23 covered CNI plugin selection as an install-time prerequisite; §49 goes deep on how each major plugin (Calico, Flannel, Cilium, Weave) actually implements the model established here. §55 (NetworkPolicy) returns to this section's "no isolation by default" security point with the actual mechanism for restricting it.

**Next Section:** §49 — `Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md`
