# Section 34 (Part 4): Policy-Based Routing and Route Metrics

## 1. Definition

**Plain language:** Every routing concept covered so far in this Part decides where a packet goes based on one thing only: its destination address. Policy-based routing breaks that rule on purpose — it lets you route a packet differently based on *where it came from*, *what kind of traffic it is*, or almost any other characteristic you can match on, overriding the normal destination-based routing table entirely for the traffic you choose. Metrics, by contrast, are the numeric "cost" values every routing method (static, dynamic, or policy-based) uses internally to decide which of several *candidate* paths to the same place is actually the best one.

**Precise definition:** **Policy-Based Routing (PBR)** is a mechanism that forwards packets based on criteria beyond the destination IP address alone — commonly source IP address, source/destination port, protocol, packet size, or DSCP/QoS marking — by matching traffic against an access list or class and applying an explicit route-map action (typically "set next-hop to X" or "set output interface to Y") that overrides the destination-based routing table lookup for matching traffic only. PBR is evaluated *before* the normal routing table lookup on the interface where it's applied, meaning it takes effect regardless of what the destination-based routing table would otherwise say. A **route metric** is the numeric value a routing method assigns to represent the relative "cost" or "desirability" of a specific path, used to select among multiple *available, otherwise valid* candidate routes to the same destination from the *same source/protocol* — RIP's hop count, OSPF's cost, and BGP's Multi-Exit Discriminator (MED) are all examples of protocol-specific metrics, each computed and compared only within its own protocol's routes, never directly against another protocol's metric (that cross-protocol comparison is administrative distance's job, [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)).

> 💡 **Tip:** The clean way to keep PBR, metrics, and administrative distance from blurring together: administrative distance decides between different *sources* claiming the same destination; a metric decides between different *paths* offered by the same source to the same destination; and policy-based routing throws the destination-based decision out entirely for specific traffic, replacing it with a rule based on something else about the packet. All three answer "where should this packet go," but at genuinely different decision points and using genuinely different inputs.

## 2. Why This Matters

- **PBR is the standard tool for traffic engineering scenarios normal routing can't express.** Sending traffic from a specific application subnet out a dedicated low-latency link while everything else uses a cheaper default path, or steering VoIP traffic differently from bulk data traffic, are impossible with destination-based routing alone but straightforward with PBR.
- **Metric tuning is a real, frequent production task.** Adjusting OSPF interface cost to reflect true link characteristics, or configuring BGP Local Preference/MED to shape multi-homed exit traffic, directly changes real traffic patterns and is a standard part of network capacity and cost management.
- **Cloud environments increasingly expose PBR-like constructs.** AWS/Azure/GCP route tables that route based on more than plain destination CIDR (for instance, routing based on which subnet/source traffic originates from, common in more complex VPC designs) apply the same underlying PBR concept even without the traditional "route-map" terminology.
- **Misunderstanding PBR is a classic source of "why is this one server's traffic behaving differently" confusion** — PBR overrides the routing table silently from the perspective of anyone only reading `ip route show`; the actual behavior lives in a separate, easy-to-miss policy configuration.
- **This section closes Part 4's toolset**, giving infrastructure engineers the complete mental model for "how does a packet's path actually get decided" — from the basic host decision ([§25](Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md)) through table structure ([§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)), manual and automatic route population ([§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md)-[§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)), to fine-grained traffic-specific overrides (this section).

## 3. Prerequisites and Dependencies

Builds on all of Part 4, most directly [§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) (routing table structure and longest-prefix-match, the default mechanism PBR deliberately overrides) and [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) (administrative distance and metrics as cross-source and within-source tiebreakers, which this section explicitly distinguishes PBR from). No further prerequisites within this roadmap; Part 5 (Switching and VLANs) begins immediately after, addressing a different layer of the network entirely.

## 4. Architecture / Conceptual Diagram

```text
   NORMAL ROUTING (destination-based only):

   Packet: src=10.0.1.50, dst=8.8.8.8
     → Router looks up 8.8.8.8 in routing table
     → Finds 0.0.0.0/0 via ISP-A → forwards via ISP-A
     (EVERY packet to 8.8.8.8, regardless of source, takes this path)

   POLICY-BASED ROUTING (source/traffic-type override):

   PBR rule on Router's ingress interface:
     "IF source = 10.0.1.0/24 (Finance subnet) AND dst = any
      THEN set next-hop = 203.0.113.9 (dedicated low-latency link)"
     "ELSE fall through to normal routing table lookup"

   Packet: src=10.0.1.50 (Finance), dst=8.8.8.8
     → PBR rule matches (source is Finance subnet)
     → Forwarded via 203.0.113.9 — NORMAL ROUTING TABLE NEVER CONSULTED
       for this packet, even though the table itself still says
       "0.0.0.0/0 via ISP-A"

   Packet: src=10.0.2.50 (Engineering), dst=8.8.8.8
     → PBR rule does NOT match (source is not Finance subnet)
     → Falls through to normal destination-based routing table lookup
     → Forwarded via ISP-A as usual


   METRICS — choosing among candidate paths from the SAME source:

   OSPF has TWO paths to 10.0.9.0/24, both learned via OSPF:
     Path 1: via R2, cost 20
     Path 2: via R5, cost 45
   → OSPF picks Path 1 (lower cost) — metric comparison happens
     ENTIRELY WITHIN OSPF's own routes; administrative distance and
     PBR are not involved in this specific decision at all.
```

- **PBR's defining trait is that it's evaluated first, on ingress, before the destination-based routing table is even consulted for matching traffic** — this ordering is exactly what makes it possible to override what would otherwise be the correct, longest-prefix-matched destination-based route.
- **PBR is scoped to matching traffic only** — non-matching traffic (like the Engineering subnet's packet above) falls through untouched to normal routing, which is what makes PBR a surgical tool rather than a wholesale routing table replacement.
- **Metrics never cross protocol or source boundaries** — the OSPF cost comparison in the diagram happens entirely inside OSPF's own path-selection process; it has no bearing on, and isn't compared against, any static route's or BGP route's own values (that boundary-crossing comparison is exactly what administrative distance, [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md), exists for instead).

## 5. Hands-On

### 5.1 Configuring Policy-Based Routing on Linux (ip rule + Routing Tables)

**Purpose:** Route traffic from a specific source subnet through a different gateway than the system's default route, using Linux's native PBR mechanism.

**Syntax:**

```bash
ip route add default via <alt-gateway> dev <iface> table <table-id>
ip rule add from <source-subnet> table <table-id>
ip rule show
```

**Example usage and expected output:**

```bash
$ echo "100 finance" >> /etc/iproute2/rt_tables

$ ip route add default via 203.0.113.9 dev eth2 table finance

$ ip rule add from 10.0.1.0/24 table finance
$ ip rule show
0:      from all lookup local
32764:  from 10.0.1.0/24 lookup finance
32766:  from all lookup main
32767:  from all lookup default

# Traffic sourced from 10.0.1.0/24 now consults the "finance" table
# FIRST (lower priority number = evaluated first), before falling
# through to the "main" table everything else uses.
```

**Production usage example:** Multi-homed Linux-based routers and NAT gateways use exactly this `ip rule` + per-table pattern to implement source-based routing — for example, sending traffic from a specific VLAN or application tier out a dedicated network path (a private interconnect, a different ISP) while all other traffic continues using the default route, without needing a dedicated hardware PBR feature.

**Common errors:** Forgetting that `ip rule` evaluation order (the priority number) matters — a rule with a lower priority number is evaluated first, and if a broader, unintended rule is placed before a more specific intended one, traffic that should hit the specific rule may match the broader rule instead and never reach the intended policy table.

### 5.2 Tuning OSPF Interface Cost as a Metric

**Purpose:** Manually adjust a route's metric to influence path selection among multiple otherwise-valid OSPF-learned paths to the same destination.

**Syntax:**

```text
interface <name>
 ip ospf cost <value>
```

**Example usage and expected output:**

```text
Router# show ip ospf interface eth0
eth0 is up, line protocol is up
  Internet Address 10.0.1.1/24, Area 0
  Cost: 10, Type: BROADCAST

Router(config)# interface eth0
Router(config-if)# ip ospf cost 5

Router# show ip ospf interface eth0
  Cost: 5, Type: BROADCAST
```

**Production usage example:** Explicitly setting OSPF interface cost is standard practice on links whose default calculated cost (typically reference-bandwidth-divided-by-interface-bandwidth) doesn't accurately reflect the link's real desirability — for instance, deliberately raising the cost on a backup satellite or cellular WAN link so OSPF strongly prefers a primary terrestrial link under normal conditions, without needing PBR or administrative distance changes for what is fundamentally a same-protocol path-preference decision.

**Common errors:** Adjusting cost on only one end of a link — OSPF cost is configured per-interface and is directional (it represents the cost of sending traffic *out* that interface), so a link's effective cost in each direction can be tuned independently, and forgetting this asymmetry is a common source of "traffic goes out via the fast path but comes back via the slow path" confusion.

### 5.3 Comparing BGP MED to Influence Inbound Traffic from a Peer

**Purpose:** Use a BGP metric (MED) to express a preference for one entry point over another to peers, contrasted against Local Preference's outbound-facing role ([§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)).

**Syntax:**

```text
router bgp <asn>
 neighbor <peer-ip> route-map SET-MED out
route-map SET-MED permit 10
 set metric 50
```

**Example usage and expected output:**

```text
Router# show ip bgp neighbors <peer-ip> advertised-routes
   Network          Next Hop            Metric
*> 10.0.0.0/16       203.0.113.5          50
```

**Production usage example:** A multi-homed organization advertising the same prefix to the same peer AS via two different links commonly sets a lower MED (more preferred) on the link it wants that peer to send inbound traffic through — MED is explicitly a suggestion to the *receiving* AS about which of the sender's multiple entry points is preferred, contrasted with Local Preference, which governs the sending AS's own *outbound* path preference; the two attributes work on opposite sides of a peering relationship.

**Common errors:** Confusing MED with Local Preference's direction of effect — setting MED expresses a preference to influence how a *neighboring* AS routes traffic *toward* you, while Local Preference only ever affects your own AS's outbound path choice and is never advertised to neighbors at all; using the wrong one for the intended traffic-engineering goal produces no effect on the traffic direction actually intended to be influenced.

## 6. Production Usage Notes

- **PBR should be used sparingly and documented explicitly**, since it silently overrides the routing table's apparent behavior for specific traffic — a network where multiple undocumented PBR rules exist across several routers is exceptionally difficult for a new engineer to reason about or safely change.
- **Metric tuning (OSPF cost, BGP MED, RIP offset-lists) is a legitimate and common capacity/cost-management tool** — but tuning without validating actual link characteristics (real bandwidth, latency, cost per byte) risks encoding a stale or incorrect assumption into path selection that persists long after the underlying link characteristics change.
- **Cloud-native equivalents of PBR are increasingly common** (source-based routing rules in more advanced VPC/VNet designs, service-mesh-level traffic routing based on request attributes) — the conceptual pattern (match on more than destination, override the default path for matching traffic only) recurs well beyond traditional router configuration.

## 7. Security Considerations

- PBR can be (and sometimes is, legitimately) used to route specific traffic through a dedicated inspection point (an IDS/IPS or DLP appliance) that normal destination-based routing wouldn't otherwise traverse — a valid, intentional security use case, but one that depends entirely on the PBR rule being correctly and completely scoped, since any traffic that should be inspected but doesn't match the rule silently bypasses the inspection point with no error or warning.
- Because PBR overrides destination-based routing silently, a misconfigured or malicious PBR rule can redirect specific traffic to an unintended destination (a man-in-the-middle-style redirection) without changing anything visible in the standard routing table — reviewing PBR configuration should be part of the same change-control rigor applied to routing table changes generally.
- Metric manipulation (particularly BGP MED and Local Preference) can be used maliciously in a hijacking or traffic-engineering attack scenario to make an illegitimate path appear more attractive than a legitimate one — this is one of several reasons route filtering and RPKI validation ([§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) matter even when raw connectivity appears to be functioning correctly.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                      | Resolution Path                                                                                                          |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| One specific host or subnet's traffic takes a different path than the routing table appears to indicate | A policy-based routing rule matching that source is overriding the normal destination-based lookup    | Check for PBR configuration (`ip rule show`, or platform route-map/policy configuration) — the routing table alone won't reveal this |
| Traffic consistently prefers a path that seems objectively worse (higher latency, lower bandwidth) | A metric (OSPF cost, BGP MED/Local Preference) doesn't reflect the link's actual real-world characteristics | Review and, if needed, retune the relevant metric against current, real link characteristics rather than historical/default assumptions |
| Outbound and inbound traffic for the same flow take asymmetric paths through a multi-homed network | Local Preference (outbound) and MED (inbound) were configured independently without considering the resulting asymmetry, or interface cost is asymmetric | Review Local Preference/MED configuration together as a pair; confirm whether asymmetry is intentional or accidental ([§121](../Part14/Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md) covers asymmetric routing troubleshooting more broadly) |

## 9. Best Practices

- Document every PBR rule with its business justification directly alongside the configuration — because PBR overrides the visible routing table, it's the single highest-risk-of-being-forgotten configuration type covered in this Part.
- Base metric tuning decisions on measured, current link characteristics rather than assumptions or stale defaults, and revisit them periodically as link speeds and topology change.
- Keep PBR scoped as narrowly as the actual requirement demands — broad PBR rules that match more traffic than intended risk silently redirecting traffic that should have used normal routing.

## 10. Common Anti-Patterns / Mistakes

- **Using PBR as a workaround for a routing table design problem that should instead be solved with proper subnetting, summarization, or a dedicated more-specific route.** PBR is powerful specifically because it can match on non-destination criteria — using it purely as a destination-based routing patch (something a specific route or better address planning would solve just as well) adds unnecessary operational complexity.
- **Leaving default/unconsidered metrics in place across a network with meaningfully varied link characteristics**, resulting in path selection that doesn't reflect real-world path quality.
- **Configuring MED or Local Preference in isolation without considering the resulting inbound/outbound path symmetry**, producing confusing and hard-to-troubleshoot asymmetric routing that complicates everything from firewall statefulness to latency analysis.

## 11. Interview Questions

**🎯 Beginner:** _"What's the basic idea behind policy-based routing, and how is it different from normal routing?"_
**Model answer:** Normal routing decides a packet's path based only on its destination IP address, using the routing table and longest-prefix-match. Policy-based routing lets you override that default behavior for specific traffic based on other criteria — like the packet's source address, protocol, or port — so, for example, traffic from one particular subnet could be sent out a completely different path than the routing table would otherwise dictate for that same destination, while all other traffic continues to use normal destination-based routing.
_What the interviewer is probing for:_ Whether the candidate understands PBR's core distinguishing trait (matching on more than destination) rather than confusing it with ordinary route preference/metric tuning.

**🎯 Intermediate:** _"What's the difference between a routing metric and administrative distance, and when does each one actually get used?"_
**Model answer:** A metric (like OSPF cost or RIP hop count) is used to choose the best path among multiple routes to the same destination that were all learned by the same protocol or source — it's a within-source comparison. Administrative distance is used to choose between routes to the same destination that were learned from different sources or protocols entirely — a static route versus an OSPF route versus a RIP route to the identical prefix — it's a cross-source comparison, and it's evaluated before any metric comparison would even matter, since AD decides which single source's routes get trusted at all for that destination.
_What the interviewer is probing for:_ Whether the candidate keeps the within-source (metric) versus cross-source (AD) distinction clean, a common point of confusion this section and [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) both address directly.

**🎯 Senior:** _"A team implements PBR to route a specific application's traffic through a dedicated low-latency link, but a few weeks later, an unrelated team reports that failover to a backup link doesn't seem to work for that application even though it works fine for everything else. What would you investigate?"_
**Model answer:** I'd first confirm whether the PBR rule's configured next-hop/interface has any reachability tracking of its own — much like a static route ([§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md)), a PBR rule that hard-codes a next-hop with no health check will keep forwarding matching traffic to that next-hop even if it becomes unreachable, since PBR itself doesn't automatically fall back to the normal routing table's failover behavior unless explicitly configured to do so (for instance, via a tracked object or a route-map that conditionally applies only when the primary next-hop is verified reachable). This would explain exactly the reported symptom: normal (non-PBR) traffic correctly uses the routing table's own failover mechanism (static route tracking, or a dynamic protocol's convergence) when the primary path fails, while the PBR-redirected application traffic keeps blindly using its hard-coded next-hop regardless of that next-hop's actual health, because the PBR rule was never configured with equivalent failover awareness.
_What the interviewer is probing for:_ Whether the candidate recognizes that PBR, like static routing, has no inherent failover awareness and requires deliberate additional configuration (tracking) to behave correctly during a failure — connecting this section's concept back to [§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md)'s static-route reachability-tracking pattern.

**🎯 Architect:** _"You're designing a multi-tenant platform where different customer workloads need to egress through different network paths for compliance reasons (some must use a dedicated encrypted circuit, others can use standard internet egress), all within a shared underlying network fabric. How do policy-based routing and metrics factor into this design, and what are the risks of getting it wrong?"_
**Model answer:** PBR is the correct primary mechanism here, since the requirement is fundamentally about routing differently based on *which tenant/workload* traffic originates from, not based on destination — I'd design PBR rules matching on source subnet (or a more granular identifier if the platform's addressing supports it, such as a dedicated subnet-per-tenant scheme) that direct compliance-required tenants' traffic to the dedicated encrypted circuit, with all non-matching traffic falling through cleanly to standard internet egress via normal destination-based routing. Metrics play a secondary role: within the dedicated circuit's own routing (if it involves dynamic routing on the other end), appropriate cost/preference tuning ensures traffic actually takes the intended encrypted path end-to-end rather than an alternate, possibly non-compliant path if multiple options exist. The largest risk of getting this wrong is a PBR rule that's too broad or too narrow — too broad, and non-compliant traffic might inadvertently traverse the (possibly costlier or capacity-constrained) dedicated circuit; too narrow, and compliance-required traffic might silently fall through to standard internet egress, which for a compliance requirement is a much more serious failure since it may not be immediately visible or alarmed on. I'd insist on active, continuous validation (synthetic traffic tests confirming each tenant class's traffic actually egresses via its required path) rather than trusting the PBR configuration's correctness by inspection alone, precisely because PBR failures of this kind are silent from the routing table's own perspective and would otherwise only surface during a compliance audit or, worse, an actual data-handling incident.
_What the interviewer is probing for:_ Whether the candidate can apply PBR to a genuine multi-tenant compliance scenario, correctly identifies the failure modes specific to PBR's silent-override nature, and proposes active validation rather than static configuration review alone as the safeguard against a compliance-critical misconfiguration.

## 12. Common Misconceptions

1. **"Policy-based routing is just another kind of metric tuning."** PBR overrides the destination-based decision-making process entirely for matching traffic, based on criteria that have nothing to do with the destination; metrics only ever choose among paths already offered by the same source to the same destination.
2. **"A route's metric and its administrative distance can be meaningfully compared to decide the best path."** They operate at entirely different decision stages and are never compared to each other directly — AD picks the trusted source first; metric only matters after that, among routes from that already-chosen source.
3. **"PBR rules are visible in the standard routing table output."** They are not — `ip route show` (or its platform equivalent) shows the destination-based routing table only; PBR configuration lives in a separate policy/rule construct that must be checked independently.
4. **"BGP's MED and Local Preference do the same job, just with different names."** They influence opposite directions of traffic flow — Local Preference shapes your own AS's outbound path choice and is never advertised externally; MED is advertised to a neighboring AS specifically to influence that neighbor's inbound path choice toward you.

## 13. 🔑 Key Takeaways

- Policy-based routing overrides normal destination-based routing for specific matching traffic (based on source, protocol, port, or other criteria), evaluated before the standard routing table lookup — it is a surgical override tool, not a routing table replacement.
- A route metric selects the best path among multiple routes to the same destination from the same protocol/source; it is never directly compared across different protocols or sources — that cross-source comparison is administrative distance's job ([§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)).
- PBR, metrics, and administrative distance answer "where should this packet go" at three genuinely different decision points, using genuinely different inputs, and should not be conflated.
- PBR and static-style hard-coded next-hops share the same failover blind spot: neither automatically adapts to a next-hop becoming unreachable unless explicitly paired with a reachability-tracking mechanism.
- Metric tuning (OSPF cost, BGP MED/Local Preference) is a legitimate, common production traffic-engineering tool, but should be based on real, current link characteristics rather than stale defaults or assumptions.

## 14. Related Concepts & What's Next

[§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) established the destination-based, longest-prefix-match default that PBR deliberately overrides for matching traffic. [§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md) introduced the reachability-tracking pattern this section shows also applies to PBR's own failover blind spot. [§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) introduced BGP's Local Preference and MED attributes, contrasted here by direction of effect (outbound vs. inbound influence). [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) distinguished administrative distance (cross-source) from a protocol's own metric (within-source), the exact distinction this section builds on for PBR's third, independent decision axis. This closes Part 4 (Routing Fundamentals, [§25](Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md)-[§34](Section-34-Part4-Policy-Based-Routing-and-Route-Metrics.md)); Part 5 (Switching and VLANs, [§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md)-[§43](../Part5/Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md)) begins with switching fundamentals, MAC address tables, and VLAN design — a different layer of the network stack from everything covered in this Part.

**Next Section:** [§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md) — `Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md`
