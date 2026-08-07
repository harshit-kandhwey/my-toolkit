# Section 51 (Part 7): kube-proxy Modes: iptables vs. IPVS

## 1. Definition

**Plain language:** A Service's stable virtual IP doesn't do anything by itself — something on every node has to actually rewrite network traffic so that a request to a Service IP ends up at one of the real Pod IPs behind it, and that rewriting can be done in more than one way, with real performance consequences at scale.

**Precise definition:** **kube-proxy** is the node-level component responsible for implementing the Service abstraction by programming traffic-redirection rules on each node, and it supports multiple **proxy modes** that differ in how those rules are implemented. **iptables mode** (the long-standing default) programs a sequential chain of Netfilter rules that the kernel evaluates largely in order for each packet, with per-Service and per-Endpoint rule blocks. **IPVS mode** (IP Virtual Server, also a Linux kernel feature) instead uses kernel-level hash tables and supports real load-balancing algorithms (round-robin, least connection, and others), giving it effectively constant-time Service lookup regardless of how many Services or Endpoints exist, whereas iptables mode's rule-matching cost grows linearly with Service/Endpoint count.

## 2. Why This Matters

- **iptables mode's linear rule-chain evaluation becomes a real bottleneck in large clusters.** A cluster with thousands of Services and tens of thousands of Endpoints can see measurable added latency and kube-proxy reconciliation slowness purely from iptables rule-chain length — a scaling concern that doesn't exist in the same way once the kube-proxy component ([§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md)) is well understood.
- **IPVS mode directly builds on the Service abstraction ([§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md)) without changing its API surface at all** — a Deployment, its Service, and every client of that Service behave identically regardless of which kube-proxy mode is active underneath; the mode is a node-level implementation detail, not something application manifests ever reference.
- **The choice is a genuine operational decision for platform teams running large-scale clusters**, directly relevant to CKA-style troubleshooting questions where a symptom ("Service traffic is slow/inconsistent at scale") traces back to proxy-mode choice rather than a CNI plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) or DNS ([§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)) issue.

🔑 **Key Takeaway:** iptables mode evaluates a sequential, linearly-growing chain of Netfilter rules per packet; IPVS mode uses kernel hash tables with real load-balancing algorithms and near-constant-time lookup — a difference invisible to any application talking to a Service, but a meaningful operational and scaling decision for the platform team running the cluster.

## 3. Prerequisites and Dependencies

Builds directly on [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) (kube-proxy as one of the three node components) and [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) (Services — ClusterIP, NodePort, LoadBalancer, ExternalName — the abstraction kube-proxy exists to implement).

## 4. Architecture Diagram

```text
                    Client Pod → Service ClusterIP (10.96.x.x:80)
                                       │
                                       ▼
                    ┌──────────────────────────────────┐
                    │         kube-proxy (per node)    │
                    └──────────────────────────────────┘
                          │                        │
          ┌───────────────┘                        └───────────────┐
          ▼                                                        ▼
  ┌────────────────────────────┐                    ┌────────────────────────────┐
  │       iptables mode        │                    │        IPVS mode           │
  │                            │                    │                            │
  │ Netfilter chains, e.g.:    │                    │ Kernel hash table entry:   │
  │ KUBE-SERVICES              │                    │ VIP:port → real-server set │
  │  → KUBE-SVC-<hash>         │                    │                            │
  │    → KUBE-SEP-<hash1> 33%  │                    │ Real scheduling algorithm: │
  │    → KUBE-SEP-<hash2> 33%  │                    │ round-robin, least-conn,   │
  │    → KUBE-SEP-<hash3> 33%  │                    │ dest-hash, etc.            │
  │                            │                    │                            │
  │ Rule count grows linearly  │                    │ Lookup cost ~constant      │
  │ with #Services × #Endpoints│                    │ regardless of Service count│
  └────────────────────────────┘                    └────────────────────────────┘
          │                                                        │
          ▼                                                        ▼
                    Rewritten to a real Pod IP (DNAT), forwarded via CNI (§49)
```

- **Both modes ultimately do the same job** — rewrite the destination of a packet from a virtual Service IP to a real Pod IP (DNAT) — they differ only in the mechanism and its performance characteristics at scale.
- **iptables mode's per-Service chain requires a linear scan in the worst case** (mitigated somewhat by jump-chain structuring, but fundamentally sequential), while IPVS mode's use of kernel hash tables plus the `ipvsadm` framework gives O(1)-ish lookup regardless of table size.
- **IPVS mode requires kernel modules** (`ip_vs`, `ip_vs_rr`, `ip_vs_wrr`, `ip_vs_sh`, and others) to be loaded on every node — a prerequisite iptables mode does not have, since iptables/Netfilter is present on essentially all Linux distributions by default.

## 5. Hands-On: Inspecting and Switching kube-proxy Mode

### 5.1 Checking the Active kube-proxy Mode

**Purpose:** Confirm which mode a cluster is currently running before making any changes or diagnosing a scale-related Service issue.

**Syntax:**

```bash
kubectl get configmap kube-proxy -n kube-system -o yaml | grep mode
```

**Example usage and expected output:**

```bash
$ kubectl get configmap kube-proxy -n kube-system -o yaml | grep mode
    mode: "iptables"
```

**Production usage example:** This is the first check when a platform team is deciding whether a large cluster's Service-related latency symptoms are proxy-mode-related — before assuming a CNI plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) or DNS ([§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)) problem, confirming the current mode against the cluster's actual Service/Endpoint count rules out (or implicates) kube-proxy mode as a contributing factor.

### 5.2 Inspecting iptables Rules Directly on a Node

**Purpose:** See the actual Netfilter chain structure kube-proxy has programmed, useful when debugging inconsistent Service routing.

**Syntax:**

```bash
sudo iptables -t nat -L KUBE-SERVICES -n | head -20
```

**Example usage and expected output:**

```bash
$ sudo iptables -t nat -L KUBE-SERVICES -n | head -20
Chain KUBE-SERVICES (2 references)
target                  prot opt source       destination
KUBE-SVC-XPGD46QRK7WJZT7O  tcp  --  0.0.0.0/0    10.96.0.10   /* kube-system/kube-dns:dns-tcp */ tcp dpt:53
KUBE-SVC-JD5MR3NA4I4DYORP  tcp  --  0.0.0.0/0    10.96.100.5  /* default/web-app cluster IP */ tcp dpt:80
...
```

**Production usage example:** SSHing to a node and inspecting `KUBE-SERVICES`/`KUBE-SVC-*`/`KUBE-SEP-*` chains directly is a standard escalation step when `kubectl` and `kubectl describe service` both look correct but traffic still isn't landing on the expected Pods — a real fallback used before assuming a CNI-level ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) problem.

**Common errors:** Running this on a node where the mode is actually IPVS returns mostly-empty or unrelated chains (IPVS mode still uses a thin iptables layer for masquerading, but the bulk of Service routing logic lives in the IPVS tables instead) — always confirm the mode first via 5.1 before spending time reading the wrong rule set.

### 5.3 Switching to IPVS Mode

**Purpose:** Move a cluster from the default iptables mode to IPVS mode, typically done to address Service-routing performance at scale.

**Syntax:**

```bash
# Ensure IPVS kernel modules are loaded on every node first
cat <<EOF | sudo tee /etc/modules-load.d/ipvs.conf
ip_vs
ip_vs_rr
ip_vs_wrr
ip_vs_sh
nf_conntrack
EOF
sudo modprobe ip_vs ip_vs_rr ip_vs_wrr ip_vs_sh nf_conntrack

# Edit the kube-proxy ConfigMap
kubectl edit configmap kube-proxy -n kube-system
#   mode: "ipvs"

# Restart kube-proxy Pods to pick up the change
kubectl rollout restart daemonset kube-proxy -n kube-system
```

**Example usage and expected output:**

```bash
$ kubectl rollout restart daemonset kube-proxy -n kube-system
daemonset.apps/kube-proxy restarted

$ kubectl get configmap kube-proxy -n kube-system -o yaml | grep mode
    mode: "ipvs"

$ sudo ipvsadm -Ln | head -10
IP Virtual Server version 1.2.1 (size=4096)
Prot LocalAddress:Port Scheduler Flags
  -> RemoteAddress:Port           Forward Weight ActiveConn InActConn
TCP  10.96.100.5:80 rr
  -> 10.244.1.5:80                Masq    1      0          0
  -> 10.244.2.7:80                Masq    1      0          0
```

**Production usage example:** Large-scale platform teams (thousands of Services) migrate to IPVS mode during a planned maintenance window, validating the kernel module prerequisite on every node image ahead of time via configuration management, since a node missing the `ip_vs` modules will fail to route Service traffic correctly after kube-proxy restarts in IPVS mode.

**Common errors:** Switching the ConfigMap to `ipvs` without first loading the required kernel modules on all nodes results in kube-proxy Pods that either crash-loop or silently fall back to iptables mode depending on version — always verify module availability with `lsmod | grep ip_vs` on every node before rolling out the change.

## 6. Production Usage Notes

- **The default is iptables mode in most distributions and managed offerings**, and it is entirely adequate for small-to-mid-sized clusters (low hundreds of Services) — IPVS is a scale optimization, not a universally "better" default choice, and switching modes adds real operational complexity (kernel module management across the fleet) that should be justified by an actual measured need.
- **IPVS mode exposes selectable load-balancing algorithms** (`rr`, `lc`, `dh`, `sh`, and others) via the kube-proxy IPVS configuration, giving finer control over Service traffic distribution than iptables mode's effectively-random selection — relevant for teams with specific session-affinity or load-distribution requirements beyond what `sessionAffinity: ClientIP` on the Service object already provides.
- **Both modes coexist with the CNI plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)), not compete with it** — kube-proxy's mode governs Service (virtual IP) routing specifically; actual Pod-to-Pod packet delivery across nodes is still the CNI plugin's responsibility regardless of which kube-proxy mode is active.

## 7. Security Considerations

- Direct node access to inspect or modify iptables/IPVS rules is equivalent to the ability to redirect Service traffic on that node — securing SSH/node access is part of the same hardening posture that protects kube-proxy's configuration ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)).
- A misconfigured or crash-looping kube-proxy (common during a botched iptables-to-IPVS migration) can leave Services completely unreachable cluster-wide, which is an availability concern with security-incident-response implications if mistaken for an attack rather than a rollout error.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                | Resolution Path                                                                                      |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Service traffic latency grows noticeably as Service count increases  | iptables mode's linear rule-chain evaluation at high Service/Endpoint scale | Evaluate switching to IPVS mode after confirming kernel module prerequisites cluster-wide            |
| kube-proxy Pods crash-loop after enabling IPVS mode                  | Required `ip_vs*` kernel modules not loaded on the node                     | `lsmod \| grep ip_vs`; load modules via `modprobe`/`modules-load.d` before restarting kube-proxy     |
| Service works on some nodes but not others after a proxy-mode change | Kernel modules or ConfigMap change not applied consistently across nodes    | Verify module presence and kube-proxy ConfigMap/DaemonSet rollout status on every node, not just one |

## 9. Best Practices

- Confirm the actual operational need (measured Service-routing latency or reconciliation slowness at scale) before migrating from the iptables default to IPVS mode, rather than switching preemptively.
- Bake IPVS kernel module loading into the base node image or configuration-management baseline before ever flipping the kube-proxy ConfigMap, so the migration isn't blocked or partially broken by node-level drift.
- Validate the switch in a non-production cluster of similar Service/Endpoint scale first, since a wrongly-configured proxy mode can make Services intermittently or completely unreachable.

## 10. Common Anti-Patterns / Mistakes

- **Switching to IPVS mode as a default "best practice" for every cluster**, regardless of actual scale, adding kernel-module operational overhead with no measurable benefit for a small cluster.
- **Changing the kube-proxy ConfigMap's mode without first ensuring `ip_vs` kernel modules are loaded on every node**, producing crash-looping or silently-reverted kube-proxy Pods.
- **Assuming Service-routing slowness must be a CNI plugin ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) or DNS ([§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)) issue** without checking kube-proxy mode and rule/table size first, when iptables rule-chain length is a well-known, distinct contributor.

## 11. Interview Questions

**🎯 Beginner:** _"What is kube-proxy, and what does 'mode' refer to in its configuration?"_
**Model answer:** kube-proxy is the node-level component that implements Kubernetes Services by programming traffic-redirection rules so that requests to a Service's virtual IP get routed to one of the real Pod IPs behind it. "Mode" refers to which underlying mechanism it uses to do this — most commonly iptables (Netfilter rule chains) or IPVS (kernel hash-table-based load balancing) — a node-level implementation detail invisible to the Service API itself.
_What the interviewer is probing for:_ Basic understanding that kube-proxy is what actually makes the Service abstraction work, and that "mode" is an implementation choice, not an API-facing concept.

**🎯 Intermediate:** _"Explain the actual mechanical difference between iptables mode and IPVS mode."_
**Model answer:** iptables mode programs a sequential chain of Netfilter rules per Service and Endpoint — packets are matched by walking through this chain, so the matching cost grows roughly linearly with the number of Services and Endpoints in the cluster. IPVS mode instead uses the Linux kernel's IP Virtual Server subsystem, which stores Service-to-Endpoint mappings in a hash table and supports real load-balancing scheduling algorithms (round-robin, least-connection, and others) — lookup cost stays roughly constant regardless of how many Services exist. IPVS mode requires specific kernel modules (`ip_vs` and its scheduler variants) to be loaded, a prerequisite iptables doesn't have since Netfilter ships by default on virtually all Linux distributions.
_What the interviewer is probing for:_ Precise, mechanical understanding of the difference, not just "IPVS is faster."

**🎯 Senior:** _"A cluster with roughly 3,000 Services is seeing intermittent Service-routing latency spikes. How would you determine whether kube-proxy mode is a contributing factor, and what would you do about it?"_
**Model answer:** I'd first confirm the current mode via the kube-proxy ConfigMap, since at a Service count that high, iptables mode's linear rule-chain evaluation and kube-proxy's own reconciliation loop (which must rewrite the entire rule set on every Service/Endpoint change) are known, well-documented contributors to exactly this symptom. I'd corroborate with kube-proxy's own reconciliation-duration metrics and iptables rule-count on a node, rather than assuming based on Service count alone. If confirmed, I'd plan a migration to IPVS mode — validating kernel module availability across the entire node fleet via configuration management first, testing the change in a staging cluster of comparable scale, and rolling out during a maintenance window with a clear rollback path (reverting the ConfigMap and restarting the DaemonSet) — rather than flipping the setting directly in production without validation.
_What the interviewer is probing for:_ A methodical diagnosis-before-action approach, awareness of the specific mechanism (rule-chain length, reconciliation cost) rather than a vague "IPVS is better," and a safe migration plan.

**🎯 Architect:** _"You're designing the platform standard for kube-proxy mode across a fleet of clusters ranging from a few dozen to several thousand Services each. Do you standardize on one mode fleet-wide, or vary it by cluster?"_
**Model answer:** I'd generally standardize on IPVS mode fleet-wide rather than varying by cluster, provided the kernel module prerequisite is baked into the standard node image used across the fleet — the operational cost of supporting IPVS (module management) is a one-time investment in the base image, and having one consistent proxy mode across every cluster removes an entire class of environment-specific behavior differences from the operator's mental model and from incident response. I would only make an exception for constrained environments (e.g., edge or lightweight distributions like k3s) where the added kernel-module dependency isn't justified by their typically-small Service counts. This is a case where fleet-wide consistency itself has value beyond the marginal performance difference on any single small cluster.
_What the interviewer is probing for:_ Ability to reason about platform-wide standardization trade-offs (consistency and reduced cognitive/operational load) rather than optimizing each cluster in isolation.

## 12. Common Misconceptions

1. **"IPVS mode changes how Services are defined or used."** It changes only the node-level mechanism implementing Service routing; the Service API object and client behavior are completely unaffected.
2. **"IPVS is strictly better and should always be used."** It adds a real kernel-module operational dependency that iptables mode doesn't have, and its performance advantage only materializes at meaningful Service/Endpoint scale.
3. **"kube-proxy mode affects Pod-to-Pod networking."** It governs Service (virtual IP) routing specifically; Pod-to-Pod packet delivery across nodes remains the CNI plugin's ([§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) responsibility regardless of proxy mode.
4. **"Switching modes is a simple, risk-free flag flip."** It requires kernel module prerequisites to be met on every node first, and a mismatch produces crash-looping kube-proxy Pods or broken Service routing, not a graceful fallback.

## 13. 🔑 Key Takeaways

- kube-proxy implements the Service abstraction on each node; iptables and IPVS are the two primary modes for doing so.
- iptables mode uses sequential Netfilter rule chains with matching cost that grows with Service/Endpoint count; IPVS mode uses kernel hash tables with near-constant-time lookup and selectable load-balancing algorithms.
- IPVS mode requires specific kernel modules (`ip_vs` and scheduler variants) loaded on every node — a real prerequisite that must be validated fleet-wide before switching.
- The choice is invisible to any Service API object or client Pod; it is purely a node-level operational and scaling decision.
- iptables mode remains an entirely adequate default for small-to-mid-sized clusters; IPVS is a deliberate scale optimization, not a universal best practice.

## 14. Related Concepts & What's Next

[§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) introduced kube-proxy as a node component; this section covers its two primary modes in full mechanical depth. [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) covers the Service abstraction this section's routing mechanism exists to implement, and [§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md) covers the CNI plugin responsible for the separate concern of actual Pod-to-Pod packet delivery. [§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md) continues the networking stack with DNS-based service discovery, which resolves Service names to the same virtual IPs this section's proxy modes route traffic toward.

**Next Section:** [§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md) — `Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md`
