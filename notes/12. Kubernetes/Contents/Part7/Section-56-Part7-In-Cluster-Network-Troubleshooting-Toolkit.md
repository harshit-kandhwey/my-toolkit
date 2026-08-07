# Section 56 (Part 7): In-Cluster Network Troubleshooting Toolkit (dig, nslookup, netshoot, tcpdump)

## 1. Definition

**Plain language:** "The Pod can't reach the Service" is one of the most common Kubernetes support tickets, and it can be caused by any one of half a dozen unrelated layers — Pod networking, kube-proxy, DNS, Ingress, or NetworkPolicy — so having a fixed, ordered checklist of tools and checks turns a confusing multi-layer problem into a fast, mechanical process of elimination.

**Precise definition:** This section defines a **structured, ordered diagnostic toolkit** for in-cluster network connectivity failures, synthesizing every networking layer covered in this Part (CNI at [§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md), Services at [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md), kube-proxy modes at [§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md), DNS at [§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md), Ingress at [§53](./Section-53-Part7-Ingress-Ingress-Controllers.md), Gateway API at [§54](./Section-54-Part7-Gateway-API-Modern-Successor-To-Ingress.md), NetworkPolicy at [§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) into a single practical workflow — moving from the cheapest, most likely checks (Pod/Service status, DNS resolution) toward progressively lower-level tools (`netshoot`'s bundled utilities, raw `tcpdump` packet capture) only as needed, rather than jumping straight to packet-level debugging for every issue.

## 2. Why This Matters

- **Most "networking" tickets are resolved without ever touching a packet capture tool.** The large majority of connectivity failures trace back to a misconfigured Selector, a missing NetworkPolicy allow-rule, or a DNS/CoreDNS issue — all diagnosable with `kubectl` and basic DNS tools alone; reaching for `tcpdump` before ruling out these cheaper checks wastes significant time.
- **An ordered checklist prevents the common mistake of debugging the wrong layer first.** Without a structured approach, engineers often jump straight to CNI-level or packet-capture debugging when the actual cause is a one-line Service selector typo or a forgotten default-deny NetworkPolicy egress rule ([§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) — a fixed order (object status → DNS → routing → policy → packet capture) consistently finds the cheap causes before the expensive ones.
- **This toolkit is the direct network-specific instance of the general troubleshooting methodology built in Part 13** — [§97](../Part13/Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s structured methodology and [§101](../Part13/Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md)'s networking-specific troubleshooting scenarios generalize the exact ordered-elimination approach this section applies specifically to Pod/Service/DNS/Ingress connectivity.

🔑 **Key Takeaway:** Effective network troubleshooting in Kubernetes is an ordered elimination process — check object state and DNS resolution before routing, check routing before policy, and reach for raw packet capture only after every cheaper, higher-level check has been exhausted, since most real-world connectivity failures are resolved well before that point.

## 3. Prerequisites and Dependencies

Synthesizes [§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md)–[§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) in full (Pod networking model, CNI, Services, kube-proxy modes, DNS, Ingress, Gateway API, NetworkPolicy) and sets up [§97](../Part13/Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md) and [§101](../Part13/Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md) (Part 13's general and networking-specific troubleshooting methodology).

## 4. Architecture Diagram: the Diagnostic Order

```text
   "Pod A cannot reach Service B" — ordered diagnostic flow

   Step 1: Object-level sanity checks (cheapest, check first)
   ┌─────────────────────────────────────────────────────────────┐
   │ kubectl get pods,svc,endpoints -n <ns>                      │
   │ kubectl describe svc <svc>   → check Selector matches Pod   │
   │                                  labels; Endpoints non-empty│
   └───────────────────────────┬─────────────────────────────────┘
                               │ (object state looks correct)
                               ▼
   Step 2: DNS resolution (§52)
   ┌───────────────────────────────────────────────────────────┐
   │ dig / nslookup <svc>.<ns>.svc.cluster.local from a Pod    │
   │  → resolves correctly?  or NXDOMAIN / timeout?            │
   └───────────────────────────┬───────────────────────────────┘
                                 │ (DNS resolves to expected IP)
                                 ▼
   Step 3: Direct IP connectivity — isolate DNS from routing
   ┌───────────────────────────────────────────────────────────┐
   │ curl/telnet directly against the resolved ClusterIP:port  │
   │  → succeeds? isolates the issue to DNS (if this succeeds  │
   │    but name-based access failed) or below (if this fails) │
   └───────────────────────────┬───────────────────────────────┘
                                 │ (direct IP connection also fails)
                                 ▼
   Step 4: NetworkPolicy audit (§55)
   ┌───────────────────────────────────────────────────────────┐
   │ kubectl get networkpolicy --all-namespaces                │
   │  → any policy selecting source or destination Pod that    │
   │    doesn't explicitly allow this traffic?                 │
   └───────────────────────────┬───────────────────────────────┘
                                 │ (no policy blocking; still fails)
                                 ▼
   Step 5: kube-proxy / CNI-level packet inspection (§49, §51)
   ┌────────────────────────────────────────────────────────────┐
   │ netshoot ephemeral debug Pod: dig, curl, tcpdump, ss, nc   │
   │ tcpdump on source/destination node to see if packets even  │
   │ leave/arrive; iptables/ipvsadm rule inspection             │
   └────────────────────────────────────────────────────────────┘
```

- **Each step is deliberately cheaper and faster than the one below it** — object-state and DNS checks take seconds and rule out the most statistically common causes before any packet-level tool is even opened.
- **Step 3 (direct IP vs. name-based access) is the single most valuable isolation check** in the entire flow — it definitively separates "this is a DNS problem" from "this is a routing/policy/CNI problem," collapsing the remaining search space by half in one command.
- **`tcpdump` and `netshoot` are reserved for the bottom of the flow** deliberately — they answer "is a packet actually leaving/arriving," which is the right question only once higher-level explanations have been ruled out.

## 5. Hands-On: Working Through the Toolkit

### 5.1 Object-State and Endpoint Sanity Check

**Purpose:** Rule out the most common and cheapest-to-fix cause first — a Service whose selector doesn't actually match any Pod, producing empty Endpoints.

**Syntax:**

```bash
kubectl get endpoints <service> -n <namespace>
kubectl describe svc <service> -n <namespace>
```

**Example usage and expected output:**

```bash
$ kubectl get endpoints web-svc -n default
NAME      ENDPOINTS   AGE
web-svc   <none>      10m

$ kubectl describe svc web-svc -n default | grep -A2 Selector
Selector:          app=web-fronted
Endpoints:         <none>
```

**Production usage example:** An empty `ENDPOINTS` column is one of the single most common root causes of "Service unreachable" reports in practice — almost always a Selector label typo (here, `web-fronted` instead of the Pods' actual `web-frontend` label) or Pods failing readiness probes, both fixable in under a minute once spotted, well before any deeper investigation is warranted.

**Common errors:** Assuming a non-empty Endpoints list guarantees traffic works — it only confirms the Selector correctly matched Pods and those Pods are Ready; it says nothing about DNS, routing, or policy further down the chain.

### 5.2 DNS Resolution and Direct-IP Isolation Together

**Purpose:** Determine, in one pass, whether a failure is DNS-specific or a routing/policy issue below DNS — the highest-value single diagnostic step in the entire flow.

**Syntax:**

```bash
kubectl run netdebug --rm -it --image=nicolaka/netshoot --restart=Never -- sh
# inside the debug pod:
dig web-svc.default.svc.cluster.local +short
curl -m 3 http://web-svc.default.svc.cluster.local
curl -m 3 http://<resolved-clusterip>:80
```

**Example usage and expected output:**

```bash
$ kubectl run netdebug --rm -it --image=nicolaka/netshoot --restart=Never -- sh
/ # dig web-svc.default.svc.cluster.local +short
10.96.100.5
/ # curl -m 3 http://web-svc.default.svc.cluster.local
curl: (28) Connection timed out after 3000 milliseconds
/ # curl -m 3 http://10.96.100.5:80
curl: (28) Connection timed out after 3000 milliseconds
```

**Production usage example:** In this example output, DNS resolves correctly but _both_ the name-based and direct-IP requests fail identically — this immediately rules out DNS ([§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)) as the cause and points at routing (kube-proxy [§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md), CNI [§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) or NetworkPolicy ([§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) instead, directing the very next command without wasted effort re-checking DNS further.

**Common errors:** Testing only the name-based request and concluding "DNS is broken" when a direct-IP test would have shown the identical failure — the distinguishing signal is always the _comparison_ between name-based and IP-based results, not either result in isolation.

### 5.3 NetworkPolicy Audit and Packet-Level Capture

**Purpose:** Check for a blocking NetworkPolicy, then — only if that's ruled out — drop to raw packet capture to see whether traffic is leaving the source Pod's node at all.

**Syntax:**

```bash
kubectl get networkpolicy --all-namespaces
kubectl describe networkpolicy -n <namespace>

# If no policy explains it, capture packets on the node hosting the source Pod:
sudo tcpdump -i any -n host <dest-pod-ip> and port 80 -w /tmp/capture.pcap
```

**Example usage and expected output:**

```bash
$ kubectl get networkpolicy --all-namespaces
NAMESPACE   NAME                    POD-SELECTOR   AGE
default     default-deny-all        <none>          2h
default     allow-frontend-to-api   app=api         2h

$ sudo tcpdump -i any -n host 10.244.2.7 and port 80
listening on any, link-type LINUX_SLL2
14:22:01.123456 IP 10.244.1.5.51322 > 10.244.2.7.80: Flags [S], seq 123456789
14:22:04.123456 IP 10.244.1.5.51322 > 10.244.2.7.80: Flags [S], seq 123456789
(no SYN-ACK ever returned — destination never responds)
```

**Production usage example:** A SYN packet leaving the source but never receiving a SYN-ACK (as shown) points at either the destination Pod/node dropping the packet (worth checking `iptables`/`ipvsadm` rules on the destination node next, [§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md)) or the destination Pod's application itself not listening on the expected port — a very different, and much narrower, next step than if `tcpdump` had shown no packet leaving the source node at all (which would instead point at the source node's own CNI/routing configuration).

**Common errors:** Running `tcpdump` on the wrong node (the source Pod's node when the packet is actually being dropped at the destination, or vice versa) wastes a capture cycle — when in doubt, capture simultaneously on both source and destination nodes to see exactly where the packet stops.

## 6. Production Usage Notes

- **`netshoot` (the `nicolaka/netshoot` image) is the standard, widely-adopted "kitchen sink" debug image** bundling `dig`, `curl`, `tcpdump`, `nc`, `ss`, `iperf`, and dozens of other tools in one place, specifically so an engineer doesn't need to `kubectl exec` into a production application container (which frequently lacks any of these tools, or even a shell) to run basic network diagnostics.
- **Ephemeral containers (`kubectl debug`, [§92](../Part12/Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)) are increasingly the preferred way to attach a debug toolset to an already-running Pod's network namespace** without needing to run a brand-new standalone debug Pod — particularly valuable when the suspected issue is specific to that exact Pod's network namespace rather than a general node-level or Service-level problem.
- **Node-level `tcpdump` requires node access (SSH or a privileged debug Pod/DaemonSet)**, which is often a deliberately gated, higher-privilege escalation step in production environments — teams commonly restrict who can run raw packet captures, making it appropriately the last resort in the ordered flow rather than a routine first check.

## 7. Security Considerations

- Raw packet capture (`tcpdump`) can expose unencrypted payload data (headers, and body content for non-TLS traffic) — access to run it should be restricted and audited like any other sensitive, high-privilege node-level operation ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)).
- Debug Pods/images like `netshoot` are typically run with elevated capabilities or `hostNetwork: true` to be useful for node-level diagnosis — treating these as temporary, tightly-scoped exceptions (removed immediately after use) rather than leaving them running is a real operational security discipline point.
- NetworkPolicy audit as part of this toolkit doubles as an informal security review opportunity — discovering an unexpectedly permissive or missing policy while troubleshooting connectivity is a common, valuable way real gaps get caught in practice.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Likely Cause                                                                                                                                                                                                                                                                              | Resolution Path                                                                                                                                                      |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Service has no Endpoints                                            | Selector/label mismatch, or backing Pods failing readiness probes                                                                                                                                                                                                                         | Compare `Selector` on the Service to actual Pod labels; check Pod readiness ([§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md))                |
| DNS resolves correctly, but connection to the resolved IP fails     | Routing (kube-proxy [§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md) or CNI [§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md)) or NetworkPolicy ([§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) issue, not DNS | Move to NetworkPolicy audit and node-level packet capture, having already ruled out DNS                                                                              |
| DNS itself fails to resolve (`NXDOMAIN` or timeout)                 | CoreDNS unhealthy, wrong name/namespace queried                                                                                                                                                                                                                                           | Check CoreDNS Pod health directly ([§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md)); confirm the exact name and namespace being queried        |
| `tcpdump` shows SYN leaving source but no SYN-ACK returned          | Destination not listening on the port, or a rule dropping the packet en route                                                                                                                                                                                                             | Check destination Pod's application/port binding; inspect destination node's iptables/ipvsadm rules ([§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md)) |
| Everything above checks out, but traffic still intermittently fails | Ingress Controller ([§53](./Section-53-Part7-Ingress-Ingress-Controllers.md)) or Gateway ([§54](./Section-54-Part7-Gateway-API-Modern-Successor-To-Ingress.md)) capacity/health issue at the edge                                                                                         | Check controller/Gateway Pod health, replica count, and resource pressure rather than assuming internal cause                                                        |

## 9. Best Practices

- Always work the checklist in order — object state, then DNS, then direct-IP isolation, then NetworkPolicy, then packet capture — rather than jumping straight to the tool that feels most technically satisfying to use.
- Keep a `netshoot`-based debug manifest or alias ready and pre-approved for use, so reaching for it during an incident isn't slowed down by first needing to figure out image names or RBAC permissions under pressure.
- Treat the DNS-vs-direct-IP comparison, shown above, as the highest-leverage single check in the whole toolkit — it should almost always be run early, since it immediately halves the remaining search space.

## 10. Common Anti-Patterns / Mistakes

- **Reaching for `tcpdump` or deep CNI-level debugging before checking Service Endpoints and DNS resolution**, spending significant time on packet-level analysis for what turns out to be a one-line Selector typo.
- **Testing only name-based connectivity and concluding "DNS is broken"** without also testing the resolved IP directly, missing the chance to isolate whether the failure is actually below DNS.
- **Forgetting to check NetworkPolicies at all**, especially in clusters where a default-deny posture ([§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) was added after initial application rollout and isn't top-of-mind for whoever is troubleshooting.

## 11. Interview Questions

**🎯 Beginner:** _"A Pod reports it can't reach a Service. What's the very first thing you'd check, and why?"_
**Model answer:** I'd start with `kubectl get endpoints <service>` and `kubectl describe svc <service>` to confirm the Service's Selector actually matches labels on Pods that exist and are Ready — an empty Endpoints list, usually from a Selector typo or failing readiness probes, is one of the single most common and cheapest-to-fix causes of "Service unreachable," and it takes seconds to check before considering anything more complex like DNS or routing.
_What the interviewer is probing for:_ Instinct to check the cheapest, most statistically likely cause first rather than jumping to complex tooling.

**🎯 Intermediate:** _"Explain why testing both the Service's DNS name and its resolved ClusterIP directly is more useful than testing either alone."_
**Model answer:** Testing only the DNS name conflates two entirely different layers — if it fails, you don't yet know whether the failure is in name resolution itself or in the routing/policy path below it. By also testing the already-resolved ClusterIP directly, you isolate the two: if the IP-based test succeeds but the name-based one fails, the problem is specifically DNS (CoreDNS health, a wrong queried name); if both fail identically, DNS is exonerated and the problem is in kube-proxy routing, the CNI plugin, or a NetworkPolicy blocking the traffic. This one comparison collapses roughly half the possible causes in a single step, which is why it's the highest-leverage check in a structured network troubleshooting flow.
_What the interviewer is probing for:_ Understanding of isolation-based debugging, not just knowledge that "you can test both."

**🎯 Senior:** _"You've confirmed Service Endpoints are healthy, DNS resolves correctly, and a direct-IP connection to the Service also fails. Walk me through your next steps."_
**Model answer:** With DNS ruled out and Endpoints confirmed healthy, I'd move to a NetworkPolicy audit next, since it's a common, purely-configuration-level cause that's cheaper to check than packet capture — listing every NetworkPolicy in the relevant namespaces and confirming none of them, combined additively, are blocking the traffic (remembering that NetworkPolicy is purely additive with no explicit deny, so I'd check for policies selecting either the source or destination Pod, not just the one I initially suspect). If NetworkPolicy checks out clean, I'd escalate to `netshoot`-based inspection and `tcpdump` on both the source and destination nodes simultaneously, specifically to see whether the packet ever leaves the source node, and if it does, whether it ever arrives at the destination — that comparison tells me definitively whether the problem is source-side CNI/routing, destination-side, or somewhere in between, rather than guessing.
_What the interviewer is probing for:_ A methodical continuation of the ordered elimination process, correctly prioritizing configuration checks (NetworkPolicy) before packet-level tools, and using dual-sided packet capture to further localize the failure.

**🎯 Architect:** _"How would you operationalize this troubleshooting toolkit across a platform team supporting dozens of application teams, so incidents get resolved consistently regardless of which engineer is on call?"_
**Model answer:** I'd formalize this ordered flow as a documented, mandatory runbook rather than tribal knowledge — codifying the exact sequence (object state → DNS → direct-IP isolation → NetworkPolicy → packet capture) so any on-call engineer, regardless of individual networking depth, follows the same cheap-to-expensive elimination order instead of ad hoc guessing. I'd pre-build and pre-approve the debug tooling (a `netshoot`-based debug Pod manifest, an ephemeral-container debug alias) so using them during an incident doesn't require re-deriving image names or requesting fresh permissions under time pressure. I'd also treat `tcpdump`/node-level access as a deliberately gated escalation tier requiring explicit elevated access, both for security reasons and to reinforce that it should genuinely be a last resort, not a habitual first move — and I'd feed real incident post-mortems back into refining the runbook, since new recurring failure patterns (e.g., a specific misconfiguration a team keeps hitting) should get folded into earlier, cheaper checks in the flow over time.
_What the interviewer is probing for:_ Ability to turn an individual diagnostic skill into a consistent, team-wide operational process, including tooling pre-provisioning and appropriate access-tier gating.

## 12. Common Misconceptions

1. **"Network troubleshooting requires deep packet-capture expertise from the start."** The large majority of real issues are resolved with `kubectl` object checks and basic DNS tools, well before packet capture is ever needed.
2. **"If DNS resolves, DNS can't be the problem."** DNS resolving correctly only rules out name resolution; it says nothing about whether the resolved IP is actually reachable — a separate, necessary check.
3. **"A NetworkPolicy that looks fine when read in isolation means NetworkPolicy isn't the cause."** Policies are additive across the whole cluster; an unrelated, forgotten policy elsewhere can still be the actual blocker.
4. **"`tcpdump` on one node is enough to diagnose a routing failure."** Capturing on only the source or only the destination node can't distinguish "never left" from "left but never arrived" — comparing both sides is what actually localizes the failure.

## 13. 🔑 Key Takeaways

- Work Kubernetes network troubleshooting as an ordered elimination flow — object/Endpoint state, then DNS, then direct-IP isolation, then NetworkPolicy, then packet capture — rather than jumping to the most complex tool first.
- The DNS-name-vs-direct-IP comparison is the single highest-leverage check, immediately separating DNS-layer failures from routing/policy-layer failures.
- `netshoot` bundles the standard toolkit (`dig`, `curl`, `tcpdump`, `nc`, `ss`) in one debug image specifically because production application containers usually lack these tools entirely.
- NetworkPolicy's additive-only model means auditing must cover every policy selecting either endpoint, not just the one policy under initial suspicion.
- Node-level packet capture is appropriately gated as a last-resort, higher-privilege step — both because most issues resolve earlier in the flow, and because raw capture access is a real security-sensitive capability.

## 14. Related Concepts & What's Next

This section synthesizes the entire networking Part — [§48](./Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md) (Pod networking model), [§49](./Section-49-Part7-CNI-Plugins-Compared-Calico-Flannel-Cilium-Weave.md) (CNI), [§50](./Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) (Services), [§51](./Section-51-Part7-kube-proxy-Modes-iptables-vs-IPVS.md) (kube-proxy modes), [§52](./Section-52-Part7-DNS-Kubernetes-CoreDNS-Service-Discovery.md) (DNS), [§53](./Section-53-Part7-Ingress-Ingress-Controllers.md) (Ingress), [§54](./Section-54-Part7-Gateway-API-Modern-Successor-To-Ingress.md) (Gateway API), and [§55](./Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) (NetworkPolicy) — into one ordered diagnostic workflow. [§97](../Part13/Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md) generalizes this same elimination-based methodology across all of Kubernetes troubleshooting, not just networking, and [§101](../Part13/Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md) returns specifically to networking troubleshooting scenarios with additional depth beyond what this Part's capstone covers. This is the final section of Part 7 — Part 8 begins immediately with Storage, starting from the most basic volume types.

**Next Section:** [§57](../Part8/Section-57-Part8-Volumes-emptyDir-hostPath-Ephemeral-Storage.md) — `Section-57-Part8-Volumes-emptyDir-hostPath-Ephemeral-Storage.md`
