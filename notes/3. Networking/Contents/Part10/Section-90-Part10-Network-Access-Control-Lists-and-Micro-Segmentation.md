# Section 90 (Part 10): Network Access Control Lists and Micro-Segmentation

## 1. Definition

**Plain language:** A traditional network firewall draws one hard line around a perimeter — everything inside is trusted, everything outside isn't. But once an attacker (or a compromised workload) gets past that one line, they can often move freely to any other system inside it. Network Access Control Lists (NACLs) and micro-segmentation are about drawing many small lines *inside* the perimeter too, so that even a compromised workload can only talk to the small handful of other things it actually needs to.

**Precise definition:** A **Network Access Control List (NACL)** is a **stateless**, ordered, numbered set of allow/deny rules evaluated against traffic crossing a network boundary (classically a subnet boundary in a cloud VPC). "Stateless" means each direction of traffic is evaluated independently — a NACL has no memory of an established connection, so return traffic for an allowed inbound request must be explicitly permitted by an outbound rule as well (contrast with the **stateful** security groups covered in [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md), where an allowed inbound connection's return traffic is automatically permitted). Rules are evaluated **in numeric order, lowest number first**, and the first matching rule wins — no further rules are consulted, which is the opposite behavior from stateful security groups where all matching allow rules are effectively unioned. **Micro-segmentation** is the broader architectural practice this section builds toward: dividing a network into many small, workload-scoped zones (down to the level of an individual service or even an individual pod/container) and enforcing least-privilege communication policies between them, rather than relying on one coarse perimeter or one flat internal network. NACLs, per-workload security groups, and identity-aware policy engines (like Kubernetes NetworkPolicy) are all mechanisms for implementing micro-segmentation at different layers.

> 💡 **Tip:** Think of a NACL as a stateless, subnet-level speed bump and a security group ([§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) as a stateful, instance-level bouncer who remembers who they let in. Micro-segmentation is the strategy of deploying many such bouncers — one per workload — instead of a single bouncer at the building's front door.

## 2. Why This Matters

- **Micro-segmentation is the practical, network-layer implementation of Zero Trust's "never trust, always verify" principle from [§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)** — instead of trusting anything already inside the perimeter, every workload-to-workload connection is explicitly evaluated against a least-privilege policy.
- **NACLs provide a second, independent layer of defense beneath security groups** — because they're stateless and evaluated at the subnet boundary rather than the instance boundary, a misconfigured security group doesn't automatically expose a workload if the NACL layer still blocks the traffic.
- **A flat internal network turns any single compromised host into a foothold for lateral movement across the entire environment** — the single most consistent finding in real-world breach post-mortems is that the initial compromise was contained to one system, but the *absence* of internal segmentation let the attacker pivot to higher-value targets.
- **Micro-segmentation dramatically shrinks the blast radius of a compromise** — a compromised web server that can only reach its specific application-tier port on its specific backend, rather than the entire internal network, limits what an attacker can do even after successful initial access.
- **Compliance frameworks (PCI-DSS, and similar) frequently mandate network segmentation explicitly** — isolating a regulated workload (payment processing, for example) onto its own segment with tightly controlled ingress/egress is often a hard audit requirement, not just a best practice.

## 3. Prerequisites and Dependencies

This section builds directly on [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)'s distinction between stateful security groups and stateless network ACLs — that section introduced the instance-level, stateful control; this section focuses on the subnet-level, stateless control and the broader segmentation philosophy both mechanisms serve. It's also a direct continuation of [§89](Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md)'s Layer 7 WAF material in the sense that both are inspection/filtering controls, but operating at opposite ends of the stack — the WAF filters HTTP application content, while NACLs and micro-segmentation filter network and transport-layer reachability between workloads, and the two are complementary rather than overlapping. Finally, this section assumes the Zero Trust principles introduced in [§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) (never trust based on network location alone, verify every connection) as its underlying architectural motivation — micro-segmentation is essentially Zero Trust applied specifically to network reachability.

## 4. Architecture / Conceptual Diagram

```text
   VPC
   ┌───────────────────────────────────────────────────────────────────┐
   │  Subnet A (public)              NACL-A (stateless, numbered)       │
   │  ┌───────────┐   inbound rule 100: ALLOW tcp/443 from 0.0.0.0/0 ►  │
   │  │  Web tier │   inbound rule 200: DENY  all from 0.0.0.0/0     ►  │
   │  └─────┬─────┘   outbound rule 100: ALLOW tcp/8080 to Subnet B  ►  │
   │        │                                                           │
   │        ► per-workload SG: only web-tier SG may send to app-tier SG │
   │        │                                                           │
   │  Subnet B (private)              NACL-B (stateless, numbered)      │
   │  ┌───────────┐   inbound rule 100: ALLOW tcp/8080 from Subnet A ►  │
   │  │  App tier │   inbound rule 200: DENY  all                   ►  │
   │  └─────┬─────┘                                                     │
   │        │                                                           │
   │        ► per-workload SG: only app-tier SG may send to db-tier SG  │
   │  Subnet C (private)              NACL-C (stateless, numbered)      │
   │  ┌───────────┐   inbound rule 100: ALLOW tcp/5432 from Subnet B ►  │
   │  │  DB tier  │   inbound rule 200: DENY  all                   ►  │
   │  └───────────┘                                                     │
   └───────────────────────────────────────────────────────────────────┘
     ◄── Each layer (NACL at subnet edge, SG at workload edge) is an
          independent policy checkpoint — traffic must pass BOTH.
```

- **NACLs sit at the subnet boundary and are stateless, evaluated in numeric order with first-match-wins** — the inbound and outbound rule sets are entirely independent, so allowing inbound traffic on a port does not implicitly allow its return traffic without a matching outbound rule.
- **Security groups ([§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) sit at the individual workload/instance boundary and are stateful** — this diagram shows both layers active simultaneously, which is the defense-in-depth pattern: even if one layer is misconfigured, the other still constrains reachability.
- **True micro-segmentation goes further than this subnet-per-tier diagram** — the per-workload security group references shown here (web-tier SG ► app-tier SG only) are the beginning of micro-segmentation; a fully micro-segmented environment defines a distinct, narrow policy for every individual workload rather than just every tier.

## 5. Hands-On

### 5.1 Writing Numbered, Stateless NACL Rules for a Subnet

**Purpose:** Demonstrate the ordered, stateless nature of NACL rule evaluation, including the requirement to explicitly permit return traffic.

**Syntax:**

```text
Rule #<number> | Type: <inbound|outbound> | Protocol: <proto> | Port range: <range> | Source/Dest: <CIDR> | Action: <ALLOW|DENY>
```

**Example usage and expected output:**

```text
# Inbound rules on the public web-tier subnet's NACL
Rule 100 | inbound  | tcp | 443       | 0.0.0.0/0        | ALLOW
Rule 110 | inbound  | tcp | 1024-65535| 0.0.0.0/0        | ALLOW   # ephemeral return ports
Rule 200 | inbound  | all | all       | 0.0.0.0/0        | DENY    # implicit/explicit default deny

# Outbound rules — must separately allow the response traffic
Rule 100 | outbound | tcp | 1024-65535| 0.0.0.0/0        | ALLOW   # responses to inbound 443 requests
Rule 200 | outbound | all | all       | 0.0.0.0/0        | DENY
```

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" https://web-tier-host.example.internal
200
# Works because inbound 443 is allowed AND outbound ephemeral ports are allowed for the response
```

**Production usage example:** Cloud NACLs are the standard "second layer" placed beneath security groups on any subnet holding sensitive workloads (database subnets, in particular), with a tight, explicit rule set permitting only the specific tiers and ports that must reach that subnet, and an explicit low-numbered deny-all as a visible backstop.

**Common errors:** Forgetting the outbound ephemeral-port rule is the single most common NACL mistake — inbound traffic on port 443 is allowed, but the server's *response* uses a high ephemeral source port, which gets silently dropped by the outbound rule set if it isn't explicitly permitted, producing a connection that appears to "hang" rather than fail cleanly.

### 5.2 Per-Workload Security Groups as Micro-Segmentation

**Purpose:** Show how referencing security groups by identity (rather than by IP/CIDR) implements fine-grained, workload-scoped micro-segmentation rather than coarse subnet-level segmentation.

**Syntax:**

```text
SecurityGroup <name>: allow <protocol>/<port> from SecurityGroup <other-name>
```

**Example usage and expected output:**

```text
# app-tier-sg only accepts traffic from web-tier-sg, regardless of IP address
SecurityGroup app-tier-sg:
  inbound: allow tcp/8080 from SecurityGroup web-tier-sg

SecurityGroup db-tier-sg:
  inbound: allow tcp/5432 from SecurityGroup app-tier-sg
```

```bash
$ # From a host in web-tier-sg
$ curl -s -o /dev/null -w "%{http_code}\n" http://app-host:8080/health
200
$ # From a host NOT in web-tier-sg or app-tier-sg, even on the same subnet
$ curl -s -o /dev/null -w "%{http_code}\n" http://app-host:8080/health
000   # connection refused/timeout — not permitted by identity
```

**Production usage example:** This is the standard three-tier micro-segmentation pattern in cloud environments — because rules reference security group identity rather than IP ranges, the policy remains correct even as instances scale up, terminate, and get replaced with new IP addresses, which a CIDR-based rule set would require constant manual updating to maintain.

**Common errors:** Referencing a broad CIDR range (an entire subnet) instead of the specific security group identity defeats the purpose of micro-segmentation — it reintroduces coarse, subnet-level trust exactly where identity-based, workload-level trust was the point.

### 5.3 Kubernetes NetworkPolicy as a Micro-Segmentation Bridge Concept

**Purpose:** Demonstrate that the same least-privilege, identity-based segmentation principle extends below the cloud-networking layer into pod-to-pod traffic within a cluster.

**Syntax:**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: <policy-name>
spec:
  podSelector: { matchLabels: { <label>: <value> } }
  policyTypes: [Ingress]
  ingress:
    - from: [{ podSelector: { matchLabels: { <label>: <value> } } }]
      ports: [{ protocol: TCP, port: <port> }]
```

**Example usage and expected output:**

```yaml
# Only pods labeled role=frontend may reach pods labeled role=backend on port 8080
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-allow-frontend-only
spec:
  podSelector:
    matchLabels:
      role: backend
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              role: frontend
      ports:
        - protocol: TCP
          port: 8080
```

```bash
$ kubectl apply -f backend-allow-frontend-only.yaml
networkpolicy.networking.k8s.io/backend-allow-frontend-only created
$ kubectl exec frontend-pod -- curl -s -o /dev/null -w "%{http_code}\n" http://backend-svc:8080
200
$ kubectl exec unrelated-pod -- curl -s -o /dev/null -w "%{http_code}\n" http://backend-svc:8080
000
```

**Production usage example:** NetworkPolicy is the same identity-based (label-selector-driven) micro-segmentation pattern from 5.2 applied one layer down, inside the cluster's own pod network — it's the natural next step once cloud-level security groups are already scoped per-tier, extending least-privilege reachability all the way to individual pods.

**Common errors:** Assuming NetworkPolicy is enforced by default — it is only enforced if the cluster's CNI plugin actually implements NetworkPolicy support; applying policy YAML against a CNI that doesn't enforce it silently has no effect at all, leaving pods fully reachable from anywhere in the cluster.

### 5.4 Host-Level Micro-Segmentation with `nft`/`iptables` Chains

**Purpose:** Show micro-segmentation enforced directly on a host, as the lowest-level, most granular layer of the defense-in-depth stack.

**Syntax:**

```text
nft add rule <table> <chain> ip saddr <allowed-source> tcp dport <port> accept
nft add rule <table> <chain> drop
```

**Example usage and expected output:**

```bash
# Only the app-tier host's specific IP may reach this host's database port
$ sudo nft add table inet filter
$ sudo nft add chain inet filter input { type filter hook input priority 0 \; }
$ sudo nft add rule inet filter input ip saddr 10.0.2.15 tcp dport 5432 accept
$ sudo nft add rule inet filter input tcp dport 5432 drop
$ sudo nft list chain inet filter input
table inet filter {
	chain input {
		type filter hook input priority filter; policy accept;
		ip saddr 10.0.2.15 tcp dport 5432 accept
		tcp dport 5432 drop
	}
}
```

**Production usage example:** Host-level `nft`/`iptables` rules are typically the last, innermost layer of micro-segmentation — applied on top of cloud NACLs and security groups as defense-in-depth for particularly sensitive hosts (database servers, secrets management systems), so that even a fully compromised network-layer control set still doesn't grant reachability the host itself refuses.

**Common errors:** Ordering the specific `accept` rule *after* a broader `drop` rule in the same chain silently defeats it, since rules are evaluated top-to-bottom and the first match wins — a mistake structurally identical to NACL rule-number ordering errors, just at the host firewall layer instead of the cloud subnet layer.

## 6. Production Usage Notes

- **NACLs are typically configured conservatively and changed infrequently** compared to security groups, since they apply to an entire subnet's traffic rather than a single workload — a mistake in a NACL rule has a much broader blast radius than a mistake in one workload's security group.
- **Well-run micro-segmentation programs maintain an explicit, documented communication matrix** (which tier/workload is permitted to reach which other tier/workload, on which ports) as source-of-truth, generating the actual NACL/security-group/NetworkPolicy rules from that matrix rather than accumulating ad hoc rules over time.
- **Default-deny is the consistent posture across every layer discussed in this section** — NACLs, security groups, NetworkPolicy, and host firewalls should all end their rule chains with an explicit deny-everything-else rule, so that any traffic pattern not explicitly documented and approved is rejected by default rather than silently permitted.

## 7. Security Considerations

- **Micro-segmentation limits lateral movement, but does not prevent initial compromise** — it's a containment control, reducing what a successfully compromised workload can reach next, not a substitute for the endpoint and application-layer defenses that prevent the initial compromise in the first place.
- **Stateless NACL rules are easy to get subtly wrong in exactly the way shown in 5.1** — a missing outbound ephemeral-port rule doesn't produce an obvious, loud failure; it produces intermittent-looking connectivity issues that are harder to diagnose than an outright block.
- **Layering NACLs, security groups, NetworkPolicy, and host firewalls is deliberate redundancy, not wasted effort** — a misconfiguration in any single layer is caught by the layers around it, which is the same defense-in-depth reasoning already applied to the WAF-plus-application-code relationship in [§89](Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                   | Resolution Path                                                                                                    |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Connections appear to hang or time out rather than being cleanly refused | A NACL is missing the outbound rule permitting ephemeral-port return traffic for an otherwise-allowed inbound connection | Add an outbound rule allowing the ephemeral port range (typically 1024-65535) to the relevant destination |
| A workload can reach another workload it shouldn't be able to           | A security group or NACL rule references a broad CIDR range instead of a specific security group identity or narrow subnet | Replace the CIDR-based rule with an identity-based (security group) reference scoped to only the intended source |
| A Kubernetes NetworkPolicy is applied but traffic is still unrestricted | The cluster's CNI plugin does not enforce NetworkPolicy resources                                    | Verify the CNI plugin's NetworkPolicy support before relying on policy YAML; switch to or add a policy-enforcing CNI if needed |
| An `nft`/`iptables` rule intended to block traffic has no effect        | The blocking rule is ordered after a broader accept rule in the same chain, so the earlier rule matches first | Reorder the chain so specific accept/deny rules precede broader catch-all rules, matching the numeric-order-matters pattern from NACLs |

## 9. Best Practices

- Maintain an explicit, documented communication matrix (which workload may reach which, on which ports) as the source of truth, and generate NACL, security group, and NetworkPolicy rules from it rather than accumulating undocumented ad hoc rules.
- Prefer identity-based rules (security group references, Kubernetes label selectors) over IP/CIDR-based rules wherever the mechanism supports it, since identity-based rules remain correct as instances and pods scale and get replaced.
- Apply default-deny consistently at every layer — NACL, security group, NetworkPolicy, and host firewall — so any traffic pattern not explicitly approved is rejected rather than silently allowed through a gap in one layer.

## 10. Common Anti-Patterns / Mistakes

- **Relying on a single flat internal network with no segmentation beyond the outer perimeter firewall.** This is the exact anti-pattern micro-segmentation exists to fix — a single compromised host becomes a foothold for unrestricted lateral movement across the entire environment.
- **Using broad CIDR ranges in security group or NACL rules where identity-based references (security group IDs, Kubernetes label selectors) are available.** This reintroduces coarse, location-based trust exactly where the goal was fine-grained, workload-based trust.
- **Forgetting that NACLs are stateless and require explicit outbound rules for return traffic.** This produces intermittent, hard-to-diagnose connectivity failures rather than a clean, obvious block, wasting significant troubleshooting time.

## 11. Interview Questions

**🎯 Beginner:** _"What's the key functional difference between a security group and a network ACL?"_
**Model answer:** A security group is stateful and applies at the individual instance/workload level — if you allow inbound traffic on a port, the return traffic is automatically permitted without a separate outbound rule. A network ACL is stateless and applies at the subnet boundary — inbound and outbound rules are evaluated completely independently, so return traffic for an allowed inbound connection must be explicitly permitted by a separate outbound rule, or the connection will fail.
_What the interviewer is probing for:_ Whether the candidate has internalized the stateful-vs-stateless distinction well enough to predict real troubleshooting scenarios, not just recite the definitions.

**🎯 Intermediate:** _"Why would you use both security groups and NACLs together instead of just one?"_
**Model answer:** They provide independent layers of defense at different scopes — security groups at the individual workload level, NACLs at the subnet level. A misconfiguration in one layer (an overly permissive security group rule, for example) doesn't automatically expose the workload if the NACL at the subnet boundary still restricts the traffic. This is defense-in-depth: the two layers are redundant by design, so a single mistake in either one is caught by the other.
_What the interviewer is probing for:_ Understanding of defense-in-depth as a deliberate architectural choice, not confusion about which single tool is "better."

**🎯 Senior:** _"Your team wants to move from tier-based segmentation (web/app/db subnets) to true micro-segmentation (per-workload policies). What's involved in that transition, and what's the biggest practical challenge?"_
**Model answer:** Tier-based segmentation groups many workloads into one policy scope (all app-tier hosts share one security group, for example), while true micro-segmentation defines a distinct, narrow policy per individual workload or service. The transition requires first building an accurate communication matrix — knowing exactly which workload actually needs to talk to which other workload, on which ports — which is often harder than it sounds in an existing environment where undocumented dependencies have accumulated over time. The biggest practical challenge is usually discovery, not enforcement: teams frequently don't have full visibility into their own application's actual traffic patterns, so writing overly narrow policies risks breaking legitimate but undocumented communication paths. I'd address this by deploying new, narrower policies in a monitoring/log-only mode first where the tooling supports it (mirroring the staged rollout pattern used for IDS/IPS in [§87](Section-87-Part10-Intrusion-Detection-Prevention-Systems-IDS-IPS-Conceptual-Overview.md) and WAF rules in [§89](Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md)), validating against real traffic before enforcing, and iterating the communication matrix based on what's actually observed rather than what's assumed.
_What the interviewer is probing for:_ Recognition that the operational challenge is discovery and validation, not just writing policy syntax, and the ability to apply the same staged-rollout risk-mitigation pattern from other security domains to this one.

**🎯 Architect:** _"You're designing network segmentation for a large environment spanning multiple cloud VPCs, on-prem data centers, and Kubernetes clusters. How do you keep the segmentation policy coherent across such heterogeneous enforcement points?"_
**Model answer:** I would start from a single, environment-wide communication matrix expressed in terms of workload identity and intent (service A may call service B on port X) rather than infrastructure-specific constructs, treating that matrix as the source of truth independent of where any given workload happens to run. From that shared source, I'd generate the enforcement-point-specific artifacts for each layer — cloud security groups and NACLs for VPC-hosted workloads, Kubernetes NetworkPolicy for cluster-internal traffic, and host-level `nft`/`iptables` rules or an identity-aware service mesh policy for on-prem or particularly sensitive hosts — so that the same intent is consistently enforced regardless of the underlying platform's native mechanism. I would insist on default-deny as the baseline at every one of those enforcement points, since a segmentation strategy is only as strong as its weakest platform's default posture. For cross-boundary traffic specifically (VPC to on-prem, cluster to VPC), I'd treat each boundary crossing as its own explicit policy decision rather than assuming transitive trust just because two systems are each individually well-segmented internally. Finally, I'd build drift detection that periodically compares each platform's actual enforced rules back against the source-of-truth communication matrix, since heterogeneous enforcement points managed by different teams with different tooling are exactly the conditions under which policy silently drifts out of sync with intent over time.
_What the interviewer is probing for:_ Ability to think in terms of a platform-independent policy model with per-platform enforcement, awareness that cross-boundary trust must never be assumed transitively, and attention to long-term drift rather than just initial design.

## 12. Common Misconceptions

1. **"NACLs and security groups do the same job, so only one is needed."** They operate at different scopes (subnet vs. workload) and with different semantics (stateless vs. stateful) — using both is deliberate defense-in-depth, not redundancy to be trimmed away.
2. **"Micro-segmentation is only relevant to cloud environments."** The same identity-based, least-privilege reachability principle applies equally to Kubernetes clusters (NetworkPolicy) and individual hosts (`nft`/`iptables`); it's an architectural pattern, not a single cloud-specific feature.
3. **"A NACL rule blocking traffic will always produce an obvious, immediate failure."** A missing return-traffic rule (the ephemeral-port scenario in 5.1) instead produces a connection that appears to hang, which is often harder to diagnose than a clean rejection.
4. **"Segmenting the network is sufficient on its own to stop an attacker who gets in."** Micro-segmentation limits lateral movement after a compromise; it does not prevent the initial compromise, which still requires the endpoint, application, and identity-layer defenses covered elsewhere in this knowledge base.

## 13. 🔑 Key Takeaways

- NACLs are stateless, numbered, subnet-boundary rules evaluated in order with first-match-wins, requiring explicit outbound rules for return traffic — a fundamentally different model from stateful security groups ([§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)).
- Micro-segmentation is the network-layer implementation of Zero Trust ([§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)): dividing the network into many small, workload-scoped zones with least-privilege reachability, rather than relying on one coarse perimeter.
- The same identity-based segmentation principle spans multiple layers — cloud security groups, Kubernetes NetworkPolicy, and host-level `nft`/`iptables` rules — each enforcing least-privilege reachability at a different point in the stack.
- Defense-in-depth across NACLs, security groups, NetworkPolicy, and host firewalls means a misconfiguration in any single layer is caught by the layers around it.
- Segmentation limits lateral movement and blast radius after a compromise; it is not a substitute for the controls that prevent the initial compromise.

## 14. Related Concepts & What's Next

This section closes Part 10 by extending [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)'s stateful-vs-stateless distinction into the broader micro-segmentation philosophy, and by connecting that philosophy explicitly to the Zero Trust principles introduced in [§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md). Alongside [§87](Section-87-Part10-Intrusion-Detection-Prevention-Systems-IDS-IPS-Conceptual-Overview.md)'s IDS/IPS, [§88](Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md)'s DDoS mitigation, and [§89](Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md)'s WAF material, this section completes Part 10's survey of the major network security control categories — perimeter detection, volumetric defense, application-layer filtering, and now internal segmentation — each addressing a different point in an attacker's path rather than duplicating the others' coverage.

**Next Section:** [§91](../Part11/Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md) — Part 11, Section 1 (VPN Fundamentals: Why Tunnel Traffic — not yet authored)
