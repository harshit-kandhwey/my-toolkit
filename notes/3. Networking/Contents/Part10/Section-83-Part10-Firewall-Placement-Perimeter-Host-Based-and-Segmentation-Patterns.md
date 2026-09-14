# Section 83 (Part 10): Firewall Placement: Perimeter, Host-Based, and Segmentation Patterns

## 1. Definition

**Plain language:** A firewall's value depends heavily on *where* it sits, not just how it filters. A firewall at the network's edge (perimeter) stops obviously bad traffic from the outside world before it reaches anything internal. A firewall on each individual server (host-based) stops an attacker who's already gotten past the edge from moving further. A firewall between internal segments (segmentation) limits how far a compromise can spread once it's inside at all. Real production networks use all three layered together — none of them alone is sufficient.

**Precise definition:** **Perimeter firewalling** places filtering at the boundary between an organization's network (or a cloud VPC/VNet) and an untrusted external network (typically the public internet), controlling north-south traffic. **Host-based firewalling** places filtering on the individual endpoint itself (a Linux host's `iptables`/`nftables`/`firewalld`, [§85](Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md), or a cloud instance's security group, [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) so that each machine independently enforces its own allowed-traffic policy regardless of network topology. **Segmentation firewalling** places filtering between internal network zones (application tier to database tier, one VLAN to another, one VPC subnet to another) to control east-west traffic between systems that are all nominally "inside" the perimeter already. The combination of all three is the practical implementation of **defense in depth**: no single layer is assumed sufficient, and a failure or bypass at one layer is caught by another.

> 💡 **Tip:** A useful diagnostic question for any given firewall rule you're evaluating: "if the perimeter firewall didn't exist, would this rule alone stop anything bad?" If the answer for most of your rule set is no, you likely have perimeter-only firewalling with no real segmentation — a topology where one compromised host has unrestricted lateral access to everything else "inside."

## 2. Why This Matters

- **"Castle-and-moat" perimeter-only security is the single most common and most dangerous legacy pattern** still found in production networks — it assumes everything inside the perimeter is trustworthy, which fails catastrophically the moment any single internal host is compromised (phishing, a vulnerable dependency, a misconfigured public-facing service).
- **Host-based firewalls matter even inside a "trusted" network** because they are the last line of defense against lateral movement — an attacker who compromises one host in a flat, unsegmented network faces essentially no further resistance without them.
- **Segmentation directly bounds blast radius**, the same concept already established for broadcast domains in Part 5 ([§37](../Part5/Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)) — a compromised web server in a properly segmented network cannot directly reach the database tier's network path at all, regardless of credentials.
- **Cloud environments make all three placement patterns cheap and near-universal** — security groups ([§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) give every instance host-level-equivalent stateful filtering by default, which is a meaningful security improvement over the on-prem era where host firewalls were often skipped for performance or operational-simplicity reasons.
- **This placement thinking directly underlies Zero Trust networking** ([§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)), which takes segmentation to its logical extreme: no traffic is trusted by network location at all, perimeter or otherwise.

## 3. Prerequisites and Dependencies

This section depends on [§82](Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)'s stateless-vs-stateful distinction, since the placement pattern chosen often correlates with which filtering model is practical at that location (perimeter devices are frequently stateful appliances; NACLs, a stateless segmentation tool, are covered specifically in [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) and [§90](Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md)). It also draws on the broadcast-domain and VLAN segmentation concepts from Part 5 ([§37](../Part5/Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md), [§38](../Part5/Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)), since VLAN boundaries are a classic physical/logical location at which segmentation firewalling is applied. [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) (Security Groups vs. Network ACLs) and [§85](Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md) (Linux Firewalling) are the concrete tools that implement the host-based and segmentation patterns described conceptually here. [§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) (Zero Trust) is the direct conceptual extension of this section's segmentation pattern taken to its logical end state.

## 4. Architecture / Conceptual Diagram

```text
                              PERIMETER
                       ┌─────────────────────┐
   Internet ─────────► │  Edge Firewall / NAT │  ◄── north-south traffic,
                       │   Gateway / WAF      │      internet-facing filtering
                       └──────────┬───────────┘
                                  │
                    ┌─────────────┴──────────────┐
                    │        INTERNAL NETWORK      │
                    │                              │
                    │   ┌────────────────────┐     │
                    │   │  Web Tier Subnet    │     │
   SEGMENTATION ────┼──►│  (host FW on each   │     │
   boundary between │   │   instance, §84/§85)│     │
   tiers — east-west│   └──────────┬──────────┘     │
   traffic control  │              │ segmentation    │
                    │              ▼ firewall rule   │
                    │   ┌────────────────────┐     │
                    │   │  App Tier Subnet    │     │
                    │   │  (host FW per node) │     │
                    │   └──────────┬──────────┘     │
                    │              │ segmentation    │
                    │              ▼ firewall rule   │
                    │   ┌────────────────────┐     │
                    │   │  DB Tier Subnet     │     │
                    │   │  (host FW, tightest │     │
                    │   │   rule set)         │     │
                    │   └────────────────────┘     │
                    └──────────────────────────────┘

   Compromise of one web-tier host cannot reach the DB tier directly —
   it must traverse a segmentation boundary that enforces least-privilege
   access even though both are "inside" the same perimeter.
```

- **Perimeter firewalls handle the highest-volume, least-trusted traffic** (all of the internet) and are typically the most heavily hardened and heavily monitored single point in the topology — but they are also a single point whose bypass (a misconfigured public listener, a VPN vulnerability) removes the entire layer at once.
- **Host-based firewalls scale horizontally with the fleet** — every instance enforces its own policy, so there's no single device whose bypass removes protection for everything; the trade-off is that policy must be consistently applied across potentially thousands of hosts (typically via configuration management or cloud security-group templates).
- **Segmentation firewalls are placed at logical or physical tier boundaries** (subnet edges, VLAN boundaries, Kubernetes namespace boundaries in more modern stacks) specifically to control east-west movement — the traffic pattern perimeter firewalls, by design, never see at all.

## 5. Hands-On

### 5.1 Identifying Perimeter Exposure with a Port Scan (Authorized Testing Only)

**Purpose:** Confirm exactly what a perimeter firewall actually exposes to the outside world — the single most important perimeter validation step, run only against systems you own or have explicit authorization to test.

**Syntax:**

```bash
nmap -sT -p- <target-ip>
```

**Example usage and expected output:**

```bash
$ nmap -sT -p 1-1000 203.0.113.10
PORT    STATE SERVICE
22/tcp  open  ssh
443/tcp open  https
Not shown: 998 filtered ports
```

**Production usage example:** Running an authorized external scan against your own perimeter after every significant firewall rule change is a standard validation practice — catching an unintentionally exposed port (22/SSH open to the world when it should be restricted to a bastion or VPN range) before an attacker's automated scanner does.

**Common errors:** Running scans against infrastructure without authorization — many cloud providers require prior notification or explicit permission for port scanning, and unauthorized scanning of third-party or even some of your own managed infrastructure can trigger abuse investigations or violate terms of service.

### 5.2 Enforcing a Host-Based Default-Deny Policy

**Purpose:** Establish the host-based layer of defense in depth, ensuring a host protects itself even if perimeter or segmentation controls fail or are bypassed.

**Syntax:**

```bash
iptables -P INPUT DROP
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport <service-port> -j ACCEPT
```

**Example usage and expected output:**

```bash
$ sudo iptables -P INPUT DROP
$ sudo iptables -A INPUT -i lo -j ACCEPT
$ sudo iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
$ sudo iptables -A INPUT -p tcp --dport 22 -s 10.0.5.0/24 -j ACCEPT
$ sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT

$ sudo iptables -L INPUT -n -v
Chain INPUT (policy DROP)
 pkts bytes target     prot opt in     out     source          destination
    0     0 ACCEPT     all  --  lo     any     0.0.0.0/0        0.0.0.0/0
   34K   9M ACCEPT     all  --  any    any     0.0.0.0/0        0.0.0.0/0    ctstate RELATED,ESTABLISHED
    0     0 ACCEPT     tcp  --  any    any     10.0.5.0/24      0.0.0.0/0    tcp dpt:22
  1.2K  85K ACCEPT     tcp  --  any    any     0.0.0.0/0        0.0.0.0/0    tcp dpt:443
```

**Production usage example:** This exact pattern (default-deny, loopback and established-traffic exceptions, then a minimal explicit allow-list) is the standard baseline host-firewall template applied fleet-wide via configuration management (Ansible, cloud-init) so every instance self-defends identically regardless of which network segment it lands in.

**Common errors:** Setting the default policy to DROP before adding the SSH allow rule (in an active remote session), which immediately locks the administrator out of the host — always append the ESTABLISHED/RELATED and specific-allow rules *before* changing the default policy, or apply changes through a mechanism with an automatic rollback safeguard.

### 5.3 Verifying Segmentation Between Tiers

**Purpose:** Confirm that segmentation rules actually prevent unauthorized east-west traffic between tiers, rather than trusting the rule set's intent.

**Syntax:**

```bash
nc -zv <target-ip> <port>
```

**Example usage and expected output:**

```bash
# From a web-tier host, attempting to reach the database tier directly on its port
$ nc -zv 10.0.30.15 5432
nc: connect to 10.0.30.15 port 5432 (tcp) failed: Connection timed out

# Confirming the app tier CAN reach it (expected, allowed path)
$ nc -zv 10.0.30.15 5432
Connection to 10.0.30.15 5432 port [tcp/postgresql] succeeded!
```

**Production usage example:** Segmentation validation like this is a standard part of a security review or compliance audit (PCI-DSS network segmentation testing is a direct real-world example) — proving the database tier is genuinely unreachable from the web tier, not just assumed to be based on the rule set's stated intent.

**Common errors:** Testing segmentation only from a single host in a tier and assuming the result generalizes to the entire tier — an inconsistently applied security group or host firewall rule (one instance missed during a template update) can leave a single host as an unintended segmentation bypass.

## 6. Production Usage Notes

- **Defense in depth is the operative principle, not any single placement pattern** — perimeter-only, host-only, or segmentation-only firewalling each leaves a specific, well-understood gap that the others cover; production topologies use all three deliberately, not redundantly.
- **Host-based firewalls are essentially free in cloud environments** (security groups, [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md), apply per-instance by default) which removes the historical excuse ("host firewalls hurt performance" or "too much overhead to manage per-host") that led many on-prem networks to skip this layer.
- **Segmentation boundaries should map to trust and blast-radius boundaries, not just convenience.** A segmentation boundary drawn along "which team owns this" lines rather than "what should never reach what" security lines tends to under-protect the highest-value assets (databases, secrets stores).

## 7. Security Considerations

- **Perimeter-only security fails completely once any single internal host is compromised** — phishing, a vulnerable public-facing service, or a supply-chain-compromised dependency are all realistic paths past a perimeter that assumes everything inside is trusted.
- **Host-based firewalls limit lateral movement even after a host is compromised** — a compromised host with a tight outbound host firewall cannot as easily reach other internal systems or exfiltrate data to arbitrary destinations, meaningfully slowing an attacker even post-compromise.
- **Segmentation is the direct, practical mitigation for "assume breach" security thinking** — if you assume any given host may eventually be compromised, the question becomes "what can it reach from there," and segmentation is the lever that answers that question narrowly rather than broadly.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                   | Resolution Path                                                                                                    |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Application works when tested from a bastion host but fails from the actual web tier | Segmentation rule between web and app tiers is missing or too restrictive                     | Explicitly test connectivity tier-to-tier with `nc`/`telnet`; compare against the intended segmentation rule set          |
| A newly provisioned instance is reachable from the internet unexpectedly | Host-based firewall wasn't applied consistently during provisioning, or perimeter rule is too broad | Audit the provisioning template/configuration management for the missing host-firewall step; tighten perimeter rules      |
| Locked out of a host after applying a new firewall policy                 | Default-deny policy was set before the administrative-access allow rule was in place              | Use an out-of-band console/serial access method to restore access; always sequence allow rules before default-deny changes |

## 9. Best Practices

- Apply all three placement layers deliberately (perimeter, host-based, segmentation) rather than relying on any single one — treat each as covering a distinct, non-overlapping failure mode.
- Draw segmentation boundaries along blast-radius and trust lines (what should this tier never be able to reach) rather than organizational convenience.
- Validate segmentation empirically (§5.3's approach) as part of routine security review, rather than trusting that the rule set's stated intent matches its actual enforced behavior.

## 10. Common Anti-Patterns / Mistakes

- **Relying entirely on a perimeter firewall and treating the internal network as implicitly trusted.** This "castle-and-moat" pattern fails completely the moment a single internal host is compromised, since there is no further resistance to lateral movement.
- **Skipping host-based firewalls because "the security group/perimeter already handles it."** Layers are meant to be independent and redundant, not substitutes for each other — a security group misconfiguration with no host-firewall backstop removes the entire protection at once.
- **Drawing segmentation boundaries around organizational or deployment convenience rather than actual trust and sensitivity levels.** A segmentation scheme that groups the database tier with lower-trust services because "they're deployed together" defeats the purpose of segmentation.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a perimeter firewall and a host-based firewall?"_
**Model answer:** A perimeter firewall sits at the boundary between the internal network and the outside world (typically the internet), controlling north-south traffic entering or leaving the network as a whole. A host-based firewall runs on an individual machine and controls only traffic to and from that specific host, regardless of where it sits in the network. Both matter because a perimeter firewall alone leaves internal hosts undefended against each other if the perimeter is ever bypassed.
_What the interviewer is probing for:_ Basic understanding that firewall placement, not just filtering logic, is a distinct design dimension.

**🎯 Intermediate:** _"Why would you put a firewall between your web tier and your database tier if both are already behind the same perimeter firewall?"_
**Model answer:** This is segmentation, and it exists to limit lateral movement — the perimeter firewall only protects against external threats, but a compromised web-tier host (via a vulnerable dependency or application-level exploit) is now an internal, trusted-by-location attacker as far as the perimeter is concerned. A segmentation rule between the web and database tiers ensures that even a fully compromised web server cannot reach the database directly, containing the compromise's blast radius to the tier it started in rather than the whole internal network.
_What the interviewer is probing for:_ Whether the candidate understands defense in depth as addressing distinct threat models (external vs. already-inside) rather than treating firewalling as a single monolithic control.

**🎯 Senior:** _"A security audit finds that your organization has a well-configured perimeter firewall but no segmentation and no host-based firewalls internally. How would you characterize the risk, and what would you prioritize first?"_
**Model answer:** I'd characterize this as a classic castle-and-moat posture: strong at the edge, essentially flat and undefended internally. The risk is that any single successful compromise — a phished credential, a vulnerable public-facing service, a supply-chain issue — gives an attacker unrestricted lateral access to everything inside, including the highest-value assets like databases and secrets stores. I'd prioritize host-based firewalls first, since they're typically the fastest and cheapest to roll out fleet-wide (especially in cloud environments where security groups are near-free) and immediately reduce lateral-movement risk without requiring a topology redesign. I'd follow with segmentation between tiers based on data sensitivity — isolating the database and any secrets-management tier first, since that's where a successful lateral-movement attack does the most damage.
_What the interviewer is probing for:_ Ability to triage and sequence a remediation plan based on risk and blast radius, not just list all the things that are theoretically missing.

**🎯 Architect:** _"How does the perimeter/host-based/segmentation model evolve when an organization is migrating from a single on-prem data center to a multi-account, multi-region cloud footprint?"_
**Model answer:** The core defense-in-depth principle stays the same, but the natural placement points shift. On-prem, the perimeter is usually a small number of physical devices at defined network edges; in a multi-account cloud footprint, "perimeter" becomes a per-account or per-VPC boundary (internet gateways, NAT gateways, and any WAF/edge layer, [§89](Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md)) that must be consistently enforced across every account rather than a single chokepoint — this is a genuine architectural shift, since there's no longer one physical wire to control. Host-based firewalling maps almost directly onto security groups ([§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) attached per-instance, and becomes dramatically easier to apply consistently at scale via infrastructure-as-code templates rather than manual host configuration. Segmentation shifts from VLANs to VPC/subnet boundaries and, increasingly, to identity- and workload-based controls (service mesh mTLS, IAM-scoped access) rather than purely network-location-based rules — which is really the on-ramp to Zero Trust thinking ([§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)). The overall lesson for the migration: don't assume the cloud's default security groups alone constitute "done" — segmentation and consistent perimeter enforcement across every account/VPC still has to be deliberately designed, just with different primitives than on-prem.
_What the interviewer is probing for:_ Whether the candidate can translate a foundational security model across a genuine architectural shift (single data center to multi-account cloud) rather than assuming the same physical mental model just transfers unchanged.

## 12. Common Misconceptions

1. **"A strong perimeter firewall means the internal network doesn't need its own protections."** This is exactly the castle-and-moat failure mode — a single internal compromise removes all protection if there's nothing behind the perimeter.
2. **"Host-based firewalls are redundant if security groups already exist in the cloud."** Security groups typically *are* the host-based layer in cloud environments ([§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) — the point is that this layer must exist somewhere, whether implemented as a literal per-instance firewall or a cloud-native equivalent; skipping it entirely is the actual mistake.
3. **"Segmentation is only relevant for large enterprises with complex networks."** Even a small three-tier application benefits meaningfully from segmenting its database tier from its web tier — blast-radius containment scales down, not just up.
4. **"East-west and north-south traffic need the same filtering approach."** They typically don't — perimeter (north-south) filtering deals with a large volume of untrusted, internet-sourced traffic, while segmentation (east-west) filtering deals with a smaller volume of traffic between systems that share infrastructure but shouldn't share trust.

## 13. 🔑 Key Takeaways

- Perimeter, host-based, and segmentation firewalling address three distinct threat models — external attackers, post-compromise lateral movement, and inter-tier blast-radius containment — and none substitutes for the others.
- Castle-and-moat (perimeter-only) security fails completely once any single internal host is compromised, which is a realistic, common event, not an edge case.
- Cloud security groups make host-based firewalling near-free to apply fleet-wide, removing the historical performance/management excuses that led many on-prem networks to skip it.
- Segmentation boundaries should be drawn along trust and blast-radius lines (what should this tier never reach) rather than organizational or deployment convenience.
- Migrating from on-prem to cloud shifts the concrete implementation of each layer (VLANs to VPC/subnet boundaries, physical devices to per-account edge controls) but the underlying defense-in-depth principle is unchanged.

## 14. Related Concepts & What's Next

[§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) makes the host-based and segmentation patterns concrete in cloud terms — security groups as the host-based layer, network ACLs as a stateless segmentation layer at the subnet boundary. [§85](Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md) covers the Linux tooling (`iptables`/`nftables`/`firewalld`) that implements host-based firewalling on real hosts, exercised only briefly in this section's §5.2. [§86](Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) (Zero Trust) extends this section's segmentation pattern to its logical conclusion, where network location is no longer a trust signal at all. [§37](../Part5/Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) (broadcast domains) and [§38](../Part5/Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) (VLANs) from Part 5 remain the underlying Layer 2/3 primitives that on-prem segmentation boundaries are often built from.

**Next Section:** [§84](Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) — `Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md`
