# Section 121 (Part 14): Routing and Path Troubleshooting (Asymmetric Routing, Route Leaks)

## 1. Definition

**Plain language:** Sometimes a connection works in one direction but fails, stalls, or behaves strangely in the other — or traffic that should stay internal suddenly shows up somewhere it shouldn't. Both symptoms point at the same underlying category of problem: the path packets actually take through the network doesn't match the path the engineer assumes they take.

**Precise definition:** **Asymmetric routing** occurs when the forward path a packet takes from source to destination differs from the return path taken by the corresponding reply traffic — a condition that is often perfectly legal from a pure reachability standpoint but breaks stateful devices (firewalls, NAT gateways, load balancers) that expect to see both directions of a flow on the same interface or device. A **route leak** occurs when routing information (most commonly BGP prefixes) that should have remained confined to one routing domain or scope is unintentionally advertised into another, causing traffic to be pulled through a path that was never intended to carry it — ranging from a minor inefficiency to a full route hijack that black-holes or intercepts traffic. Both problems share a diagnostic signature: symptoms that don't match what the routing table on any single host claims should happen, because the actual multi-hop path is the thing in question, not any one device's local configuration.

> 💡 **Tip:** Whenever a problem "only happens sometimes" or "only affects some destinations," and simple connectivity/port tests ([§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md), [§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md)) don't explain it, treat asymmetric routing or a partial route leak as a leading hypothesis before looking for anything more exotic — both produce exactly that kind of inconsistent, path-dependent symptom.

## 2. Why This Matters

- **Asymmetric routing is invisible to single-ended tools** — a `ping` or `traceroute` from one host only shows that host's outbound path; the return path is a completely separate question that requires either a matching test from the other end or path-level evidence from both directions.
- **Stateful network devices assume symmetric flows**, so asymmetric routing is a common root cause of intermittent connection resets or drops that appear only under specific traffic patterns (e.g., multi-homed egress, ECMP, or multi-NIC hosts) rather than uniformly.
- **Route leaks operate at a scope most engineers never look at directly** — the interior routing table on an affected host looks completely normal, because the problem lives in how prefixes propagate between routing domains (autonomous systems, VPC route tables, on-prem/cloud boundaries), not in any single table entry.
- **Both problems can silently violate security boundaries** — a route leak can pull traffic that was meant to stay private onto a path that traverses infrastructure it was never authorized to cross, and asymmetric routing that bypasses an intended firewall on the return path can leave a supposedly protected flow only half-inspected.
- **They build directly on the dynamic-routing ([§29](../Part4/Section-29-Part4-Dynamic-Routing-Overview-IGP-vs-EGP.md)-[§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) and cloud-routing ([§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)-[§109](../Part12/Section-109-Part12-Cross-Reference-Where-AWS-Azure-GCP-Specific-Networking-Continues-in-This-Repo.md)) concepts already covered**, applying that theory to the messier, path-dependent reality of production networks where multiple valid routes often exist simultaneously.

## 3. Prerequisites and Dependencies

This section depends heavily on the routing-table and longest-prefix-match fundamentals from [§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md), static and dynamic routing concepts from [§27](../Part4/Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md)-[§29](../Part4/Section-29-Part4-Dynamic-Routing-Overview-IGP-vs-EGP.md), and the path-vector/BGP overview from [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md), since diagnosing a route leak requires understanding how BGP path selection and prefix propagation actually works. It also depends on the connectivity-testing toolkit from [§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md) (`traceroute`/`mtr`) and the packet-capture skills from [§118](Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md), both of which supply the raw evidence needed to detect an asymmetric path in the first place. On the cloud side, it assumes familiarity with route tables, VPC/VNet peering, and transit-gateway/hub architectures from [§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md), [§103](../Part12/Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md), and [§104](../Part12/Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md), since route leaks in modern infrastructure most often originate in a misconfigured cloud route table or an overly permissive peering/transit relationship rather than in classic on-prem BGP. It follows [§120](Section-120-Part14-DNS-Troubleshooting-Workflows.md)'s DNS-troubleshooting workflow in the escalation path from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md) — once name resolution and basic connectivity are confirmed correct, path-level routing behavior is the next layer to examine when symptoms remain unexplained.

## 4. Architecture / Conceptual Diagram

```text
   SYMMETRIC vs ASYMMETRIC ROUTING

   Symmetric (expected by stateful devices):

   Client ──►[FW/NAT]──►[Router A]──► Internet ──► Server
   Client ◄──[FW/NAT]◄──[Router A]◄── Internet ◄── Server
              (same device sees both directions)

   Asymmetric (breaks stateful inspection):

   Client ──►[FW/NAT]──►[Router A]──► Internet ──► Server
   Client ◄─────────────[Router B]◄── Internet ◄── Server
              (Router B never saw the outbound SYN —
               the return traffic looks unsolicited to it)


   ROUTE LEAK (SIMPLIFIED)

   AS 65001 (internal, "private" prefix 10.0.0.0/16)
        │
        │  intended: advertised ONLY inside AS 65001
        ▼
   [Router with misconfigured redistribution/no filtering]
        │
        │  LEAK: prefix re-advertised outward
        ▼
   AS 65002 (external peer/customer)
        │
        ▼
   Traffic destined for 10.0.0.0/16 now transits AS 65002's
   infrastructure — a path never intended, authorized, or secured
```

- Asymmetric routing is diagnosable only by comparing evidence from *both* ends of a flow (or capturing at a midpoint) — no single host's routing table reveals it, because each host's table is individually consistent; the inconsistency exists only in the combination of the two paths.
- Route leaks propagate through the same mechanisms that make dynamic routing powerful in the first place (redistribution, permissive peering, insufficient prefix filtering) — the fix is almost always a missing or misconfigured filter, not a fundamentally broken protocol.
- In cloud environments, the "route leak" equivalent is usually a route table entry or peering/transit-gateway association that sends traffic somewhere unintended — the underlying diagnostic pattern (traffic follows an unexpected path) is identical even though there's no BGP session to inspect directly.

## 5. Hands-On

### 5.1 Detecting Asymmetric Paths with Dual-Ended `traceroute`/`mtr`

**Purpose:** Confirm whether the forward and return paths between two hosts actually match, rather than assuming symmetry.

**Syntax:**

```bash
# Run on Host A (toward Host B) and on Host B (toward Host A) at roughly the same time
mtr -rw -c 10 <target-ip>
```

**Example usage and expected output:**

```bash
# From Host A (10.0.1.15) toward Host B (10.0.4.15):
$ mtr -rw -c 10 10.0.4.15
HOST: host-a                     Loss%   Snt   Last   Avg  Best  Wrst StDev
  1. gw-a-internal.local          0.0%    10    0.4   0.4   0.3   0.6   0.1
  2. core-rtr-1.local             0.0%    10    1.1   1.2   1.0   1.5   0.2
  3. core-rtr-3.local             0.0%    10    1.8   1.9   1.7   2.3   0.2
  4. 10.0.4.15                    0.0%    10    2.4   2.5   2.2   3.0   0.3

# From Host B (10.0.4.15) toward Host A (10.0.1.15):
$ mtr -rw -c 10 10.0.1.15
HOST: host-b                     Loss%   Snt   Last   Avg  Best  Wrst StDev
  1. gw-b-internal.local          0.0%    10    0.4   0.5   0.3   0.7   0.1
  2. core-rtr-4.local             0.0%    10    1.3   1.4   1.2   1.8   0.2
  3. 10.0.1.15                    0.0%    10    2.0   2.1   1.9   2.6   0.2
```

- The forward path transits `core-rtr-1` → `core-rtr-3`; the return path transits `core-rtr-4` and never touches either of those hops — this is a confirmed asymmetric path, and `core-rtr-4` is the first device to inspect if it hosts a stateful firewall or NAT.
- Running both directions with `-c 10` and comparing hop-by-hop is the entire technique — no special tooling beyond what [§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md) already introduced is required, only the discipline of testing from both ends.

**Production usage example:** This dual-ended comparison is the standard first step when a connection is reported as "works fine most of the time but occasionally resets" on a multi-homed host or in an environment with ECMP (equal-cost multi-path) routing, where different flows (or even different packets within a flow, in pathological ECMP configurations) can legitimately take different paths.

**Common errors:** Running the two traces at different times (minutes apart) when the path is affected by time-of-day routing changes, load-based ECMP hashing, or a recent failover — for a reliable comparison, run both directions as close together in time as possible, and repeat if results look inconsistent between runs.

### 5.2 Confirming the Local Route Selection with `ip route get`

**Purpose:** Determine exactly which route, interface, and next hop the local kernel will actually use for a given destination — removing any ambiguity about what the routing table's longest-prefix-match rule ([§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)) resolves to for a specific address.

**Syntax:**

```bash
ip route get <destination-ip>
```

**Example usage and expected output:**

```bash
$ ip route get 10.0.4.15
10.0.4.15 via 10.0.1.1 dev eth0 src 10.0.1.15 uid 1000
    cache

$ ip route get 8.8.8.8
8.8.8.8 via 10.0.1.254 dev eth1 src 10.0.1.15 uid 1000
    cache
```

- The two destinations resolve to *different* next hops and even different interfaces (`eth0` vs `eth1`) on the same host — on a multi-homed host, this is exactly the kind of per-destination routing divergence that produces asymmetric behavior if the return traffic isn't routed back through the matching interface.
- `ip route get` shows the answer the kernel will actually act on, which is more reliable than manually reading the full routing table (`ip route show`) and trying to mentally apply the longest-prefix-match rule, especially when multiple overlapping routes exist.

**Production usage example:** On hosts with multiple NICs or multiple default routes (common in environments bridging on-prem and cloud connectivity), `ip route get` against both the problem destination and a known-good destination is a fast way to confirm whether unexpected route selection — rather than anything upstream — is the proximate cause of an asymmetric path.

**Common errors:** Assuming the routing table entry with the "obviously correct" destination network is the one being used, when a more specific (longer-prefix) route elsewhere in the table actually wins per [§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)'s longest-prefix-match rule — always verify with `ip route get` against the exact destination rather than reasoning about the table by inspection alone.

### 5.3 Investigating Suspected Route Leaks with Looking-Glass and Route-Table Evidence

**Purpose:** Determine whether traffic to a given prefix is transiting an unexpected autonomous system or an unexpected cloud route table entry, which is the signature of a route leak.

**Syntax:**

```bash
# Public BGP looking-glass concept (works against any public looking-glass server or route collector)
# Query: "show me the AS path currently advertised for prefix X"
# Cloud equivalent: inspect the route table directly
aws ec2 describe-route-tables --route-table-ids <rtb-id>
```

**Example usage and expected output:**

```bash
# Conceptual looking-glass output for a leaked prefix:
BGP routing table entry for 203.0.113.0/24
Paths: (2 available)
  65002 65001 65099   <- unexpected: traffic now transits AS 65002
  65001                <- expected direct path

# Cloud route table showing an over-broad route:
$ aws ec2 describe-route-tables --route-table-ids rtb-0abc123
{
  "Routes": [
    { "DestinationCidrBlock": "0.0.0.0/0", "GatewayId": "igw-01234" },
    { "DestinationCidrBlock": "10.0.0.0/8", "TransitGatewayId": "tgw-05678" }
  ]
}
```

- The looking-glass output shows two available AS paths for the same prefix, one of which routes through an unexpected AS (`65002`) — this is the classic signature of a route leak, where the shorter or otherwise preferred path per BGP's path-selection rules is now one that was never intended to carry this traffic.
- The cloud route table example shows a `10.0.0.0/8` route pointed at a transit gateway that is broader than any single VPC's actual address range — an overly broad CIDR in a shared transit route table is the direct cloud analog of a BGP route leak, since it pulls traffic for prefixes the transit gateway's owner never intended to receive.

**Production usage example:** When traffic to an internal or partner-facing prefix suddenly shows added latency, an unexpected geographic detour, or fails a security review because it's traversing infrastructure outside the expected trust boundary, checking public looking-glass data (for internet-routed prefixes) or the relevant cloud account's route tables and transit-gateway associations (for cloud-internal prefixes) is the standard way to confirm and localize a leak.

**Common errors:** Concluding a leak is "someone else's problem" because the AS path shows a third party's AS number, without checking whether the organization's *own* redistribution or peering configuration is what caused the prefix to be exported too broadly in the first place — many real-world leaks originate from the affected organization's own misconfiguration, not from the party that ends up carrying the leaked traffic.

## 6. Production Usage Notes

- Multi-homed hosts and networks using ECMP are far more prone to asymmetric routing than simple single-path networks — any environment adopting multiple uplinks or multiple cloud connectivity paths (e.g., both a VPN and a Direct Connect/ExpressRoute-style link, [§97](../Part11/Section-97-Part11-GRE-and-Other-Tunneling-Protocols.md)-[§99](../Part11/Section-99-Part11-SD-WAN-Conceptual-Overview.md), [§108](../Part12/Section-108-Part12-Multi-Region-and-Multi-Cloud-Networking-Considerations.md)) should explicitly test for and account for asymmetric behavior during design, not discover it during an incident.
- Cloud route-table changes propagate quickly and are rarely gated by the kind of peer-review process that governs on-prem BGP configuration changes — treat route-table and peering/transit-gateway changes with the same change-control discipline as firewall rule changes, since the failure mode (unintended traffic path) is functionally similar.
- Stateful firewalls and NAT gateways are the devices most commonly broken by asymmetric routing — when investigating a suspected asymmetric-path incident, specifically check whether such a device sits on one leg of the path but not the other.

## 7. Security Considerations

- A route leak that pulls traffic through unintended infrastructure can expose traffic that was never encrypted end-to-end (or that relied on network-boundary trust rather than transport encryption) to a party who should never have had visibility into it — this is a strong argument for using TLS ([§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) even for traffic an engineer assumes will "stay internal."
- Prefix filtering (only accepting and advertising expected prefixes at every routing boundary) is the primary defense against route leaks, whether implemented as BGP prefix lists on a border router or as tightly scoped route-table and peering configurations in cloud environments — the absence of filtering, not the presence of a bug, is what turns a simple misconfiguration into an externally visible leak.
- Asymmetric routing that causes return traffic to bypass an intended firewall can leave a connection only half-inspected — a return packet the firewall never saw the corresponding outbound request for may be dropped (breaking the connection) or, worse on a permissively configured device, accepted without the security-policy checks the design intended.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                  | Resolution Path                                                                                              |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| Connection resets intermittently, worse under load                | Asymmetric path across ECMP or multiple uplinks hitting a stateful device inconsistently | Run dual-ended `mtr` ([§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md)) during the failure window; identify and consolidate the stateful device onto one path |
| Traffic to an internal prefix shows unexpected latency/detour     | Route leak via over-broad transit-gateway/peering route or BGP redistribution   | Check looking-glass/AS-path data (internet-facing) or cloud route tables (internal); tighten prefix filtering |
| `ip route get` shows a different interface than expected for a destination | Multiple default routes or overlapping static routes on a multi-homed host    | Review routing table with `ip route show`; correct route metrics/priority or remove the unintended route     |
| One direction of a flow is captured, the other never appears at the expected midpoint | Asymmetric routing bypassing the capture point entirely                       | Move the capture point, or capture at both true path endpoints per [§118](Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md)'s dual-ended technique               |

## 9. Best Practices

- Design multi-homed and multi-path network topologies with symmetric routing as an explicit requirement, not an assumption — document intended forward and return paths and periodically verify them with dual-ended `mtr`/`traceroute` rather than only after an incident surfaces the mismatch.
- Apply prefix filtering at every routing domain boundary (BGP peering points, VPC peering/transit-gateway associations) as a default posture, accepting and advertising only explicitly intended prefixes rather than broad or unfiltered ranges.
- Treat route-table and peering configuration changes in cloud environments with the same review rigor as firewall changes, given how directly a route change can redirect traffic across trust boundaries.

## 10. Common Anti-Patterns / Mistakes

- **Diagnosing a suspected routing problem using only one host's `traceroute` output.** A single-ended trace cannot reveal an asymmetric path — always test or capture from both ends before drawing conclusions about the path a flow takes.
- **Leaving cloud route tables or BGP redistribution unfiltered "to keep things simple."** This is precisely the condition that turns an intended, scoped route into a route leak the moment any adjacent configuration changes — filtering should be the default, not an afterthought added after an incident.
- **Assuming a route leak is purely an external party's fault because their AS number appears in the path.** The organization's own export/redistribution misconfiguration is very often the actual root cause, and fixing only "their side" leaves the underlying local misconfiguration in place for the next leak.

## 11. Interview Questions

**🎯 Beginner:** _"What is asymmetric routing, and why can it cause problems?"_
**Model answer:** Asymmetric routing is when the forward and return paths between two hosts differ. It causes problems because stateful devices like firewalls and NAT gateways expect to see both directions of a connection passing through them — if the return traffic takes a different path that bypasses the device that saw the outbound request, that device may drop the reply as unsolicited, or a different device that never saw the setup may reject or mishandle it.
_What the interviewer is probing for:_ Basic grasp of why path direction matters, tied to stateful device behavior.

**🎯 Intermediate:** _"How would you confirm whether a reported intermittent connection issue is caused by asymmetric routing?"_
**Model answer:** I'd run `mtr` from both hosts toward each other at roughly the same time and compare the hop-by-hop paths — if the forward and return paths diverge, especially at a hop that hosts a stateful firewall or NAT device, that's strong evidence of asymmetric routing. I'd also use `ip route get` on any multi-homed host in the path to confirm exactly which interface and next hop the kernel is actually selecting, since multiple routes to overlapping destinations are a common root cause on hosts with more than one network interface.
_What the interviewer is probing for:_ Practical, evidence-based diagnostic method rather than guesswork.

**🎯 Senior:** _"You discover that traffic between two of your company's own data centers is being routed through a third-party autonomous system. How do you investigate and remediate this?"_
**Model answer:** I'd first confirm the finding using public looking-glass data or route-collector output to see the actual AS path being advertised for the affected prefix, then check our own BGP configuration for overly permissive redistribution or missing prefix filters that could have caused the prefix to be exported more broadly than intended — this is more often the root cause than a problem originating with the third party. Once confirmed, I'd apply prefix filtering at the relevant peering points to stop advertising the prefix externally, verify the fix by re-checking the AS path, and treat the incident as a security event given that inter-datacenter traffic may have transited untrusted infrastructure, checking whether that traffic was adequately protected by transport-layer encryption independent of network-boundary trust.
_What the interviewer is probing for:_ Ownership of root cause (not just blaming the third party), combined with security-impact awareness.

**🎯 Architect:** _"How would you design a large, multi-homed network to prevent both asymmetric-routing incidents and route leaks at scale?"_
**Model answer:** I'd start by making symmetric routing an explicit design constraint for any stateful device placement — either ensuring only one path exists through any given stateful device, or deploying stateful devices in a way that's resilient to asymmetric flows (e.g., session synchronization across an active-active pair) rather than assuming symmetry will hold. For preventing route leaks, I'd enforce prefix filtering as policy at every routing domain boundary — BGP peering sessions, VPC peering, and transit-gateway route associations alike — ideally automated and validated as part of infrastructure-as-code review rather than left to manual configuration discipline. I'd also invest in continuous route-path monitoring (periodic looking-glass checks for internet-facing prefixes, automated route-table diffing for cloud environments) so that a leak or asymmetric-path regression is caught by monitoring rather than by a customer-reported incident, and I'd document the intended topology clearly enough that "is this path expected?" has a fast, authoritative answer during an incident.
_What the interviewer is probing for:_ Systemic, preventive design thinking rather than only reactive troubleshooting technique.

## 12. Common Misconceptions

1. **"If `traceroute` from my host looks fine, the path is fine."** A single-ended trace only shows the forward path — the return path is a completely separate question that requires evidence from the other end or a capture at a shared midpoint.
2. **"Route leaks always involve external BGP and internet routing."** The same failure pattern — a prefix advertised or routed somewhere it shouldn't be — happens constantly inside cloud environments via overly broad route-table entries and permissive peering/transit-gateway associations, with no BGP session involved at all.
3. **"Asymmetric routing is always a bug that must be fixed."** In some designs (certain ECMP or anycast architectures) asymmetric routing is intentional and handled by stateless or synchronized-state devices — the problem arises specifically when a *stateful, non-synchronized* device sits on only one of the asymmetric legs.
4. **"A route leak found in the AS path is automatically the fault of the AS that appears in it."** The organization whose prefix leaked is very often the one whose export or redistribution filtering was missing — the party that ends up carrying the leaked traffic just accepted what was advertised to them.

## 13. 🔑 Key Takeaways

- Asymmetric routing and route leaks share a diagnostic signature: symptoms that no single host's local configuration explains, because the problem lives in the multi-hop path or in cross-domain prefix propagation.
- Detecting asymmetric routing requires evidence from both ends of a flow (dual-ended `mtr`/`traceroute`, or a shared-midpoint capture) — single-ended testing cannot reveal it.
- Route leaks in modern infrastructure are as often a cloud route-table or peering/transit-gateway misconfiguration as they are a classic BGP redistribution error — the same prefix-filtering discipline defends against both.
- Stateful devices (firewalls, NAT gateways) are the components most commonly broken by asymmetric routing, and are the first place to look once an asymmetric path is confirmed.

## 14. Related Concepts & What's Next

[§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md), [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md), and [§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)-[§104](../Part12/Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md) supply the routing-table, BGP, and cloud-networking foundations this section builds path-troubleshooting technique on top of. [§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md) and [§118](Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md) supply the connectivity-testing and packet-capture tools used to gather the dual-ended evidence this section's techniques depend on. [§120](Section-120-Part14-DNS-Troubleshooting-Workflows.md)'s DNS-troubleshooting workflow precedes this section in the overall diagnostic escalation path from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md), since name-resolution and basic connectivity problems are typically ruled out before path-level routing behavior becomes the focus. [§122](Section-122-Part14-MTU-Issues-and-Path-MTU-Discovery.md) continues directly into MTU issues and Path MTU Discovery, a related but distinct class of path-dependent problem where the path itself is symmetric and correctly chosen, but a link somewhere along it can't carry full-sized packets.

**Next Section:** [§122](Section-122-Part14-MTU-Issues-and-Path-MTU-Discovery.md) — `Section-122-Part14-MTU-Issues-and-Path-MTU-Discovery.md`
