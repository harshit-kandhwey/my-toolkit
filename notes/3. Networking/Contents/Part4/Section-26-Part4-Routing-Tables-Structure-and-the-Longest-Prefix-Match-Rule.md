# Section 26 (Part 4): Routing Tables: Structure and the Longest-Prefix-Match Rule

## 1. Definition

**Plain language:** A routing table is a router's (or host's) list of "if the destination looks like this, send it this way" rules. When a packet arrives, the device compares its destination address against every rule in the table and picks the *most specific* one that matches — not just any match, the single best match — then forwards the packet out the interface or next hop that rule points to.

**Precise definition:** A **routing table** (also called a **forwarding table** or, in Linux, the **FIB** — Forwarding Information Base) is an ordered collection of **routes**, where each route consists of a **destination prefix** (a network address plus prefix length/subnet mask, e.g., `10.0.2.0/24`), a **next hop** (the IP address of the next router to forward toward, or an outgoing interface for directly connected networks), a **metric** (a cost value used to rank competing routes to the same destination, [§34](Section-34-Part4-Policy-Based-Routing-and-Route-Metrics.md)), and an **administrative distance** (a value used to rank routes from different *sources* — static vs. OSPF vs. BGP — competing for the same destination, [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)). When a packet arrives, the forwarding engine evaluates every route whose prefix matches the destination address and selects the route with the **longest prefix match** — the matching route with the most specific (highest prefix-length) network — as the winner, regardless of any other route's metric or administrative distance. Only when two matching routes have the *identical* prefix length does metric/administrative distance break the tie.

> 💡 **Tip:** Longest-prefix-match is not "pick the lowest metric route" — it's "pick the most specific matching prefix first, full stop." A `/32` host route always wins over a `/24` covering the same address, and a `/24` always wins over a `/0` default route, no matter what each route's metric says. Metrics and administrative distance only matter for breaking ties *among routes with the same prefix length*.

## 2. Why This Matters

- **It's the single rule that decides where every packet goes.** Every router, Layer 3 switch, host, and cloud route table implements longest-prefix-match — misunderstanding it leads directly to misreading routing tables and misdiagnosing "wrong path" problems.
- **It explains why more specific routes silently override broader ones.** A `/32` static route injected for a single troubleshooting host, or a more specific subnet route learned dynamically, takes precedence over a `/24` or default route without any explicit "override" configuration — engineers who don't know this rule are baffled when traffic to one specific IP behaves differently from the rest of its subnet.
- **Cloud route tables use the identical rule.** AWS VPC route tables, Azure route tables, and GCP routes all resolve overlapping routes via longest-prefix-match — reading a cloud console's route table correctly requires the same mental model as reading `ip route show` output.
- **It's foundational to debugging asymmetric routing and route leaks** ([§121](../Part14/Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md)) — most "traffic takes an unexpected path" incidents trace back to an unexpected longest-prefix match, not a missing route.
- **Route summarization design** ([§28](Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md)) depends entirely on understanding that a summarized (less specific) route will always lose to any more specific route that still exists, which is precisely what makes summarization safe.

## 3. Prerequisites and Dependencies

Builds directly on [§25](Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) (what routing is, and the router's core forwarding decision) and on Part 3's CIDR/subnet-mask material ([§16](../Part3/Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md), [§17](../Part3/Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md)) — prefix length comparison is meaningless without a solid grasp of what a prefix length represents. [§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md) immediately follows by showing how routes are manually added to this table via static routing; [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) later revisits administrative distance, only briefly introduced here as a tie-breaking mechanism, in full depth.

## 4. Architecture / Conceptual Diagram

```text
   Routing table on Router R1:

   Destination           Next Hop        Interface    Metric   AD
   ─────────────────────────────────────────────────────────────
   10.0.2.15/32          10.0.1.2        eth1         0        1     (static host route)
   10.0.2.0/24           10.0.1.2        eth1         10       90    (EIGRP-learned)
   10.0.0.0/16           10.0.1.1        eth0         20       110   (OSPF-learned)
   0.0.0.0/0             203.0.113.1     eth2         1        1     (default static route)

   Incoming packet destined for 10.0.2.15:
     Matches 10.0.2.15/32  → prefix length 32   ✅ MOST SPECIFIC — WINS
     Matches 10.0.2.0/24   → prefix length 24   (matches, but less specific)
     Matches 10.0.0.0/16   → prefix length 16   (matches, but less specific)
     Matches 0.0.0.0/0     → prefix length 0    (matches everything, least specific)

   Winner: 10.0.2.15/32 via 10.0.1.2 — the /32 wins regardless of its
   metric or AD being compared to the other three; longest prefix always
   wins first.

   Incoming packet destined for 10.0.2.99 (not the specific /32 host):
     Matches 10.0.2.0/24   → prefix length 24   ✅ WINS (no /32 covers it)
     Matches 10.0.0.0/16, 0.0.0.0/0 → less specific, lose
```

- **Every route in the table is a candidate; only the longest matching prefix is used.** The router does not "stop at the first match" in table order — conceptually, it evaluates *all* matching entries and picks the most specific, though real implementations use efficient tree structures (tries) to do this in constant time rather than linearly scanning.
- **Administrative distance and metric never enter the decision above** unless two routes tie on prefix length — in the diagram, none of the four routes have the same prefix length, so AD/metric are irrelevant to this particular lookup.
- **A `0.0.0.0/0` default route matches literally everything** but is definitionally the least specific possible route (prefix length 0) — it is always the last resort, used only when nothing more specific matches.

## 5. Hands-On

### 5.1 Reading and Interpreting a Linux Routing Table

**Purpose:** Show the routing table structure — prefix, next hop, interface, metric — as it actually appears on a Linux host or router.

**Syntax:**

```bash
ip route show
ip route show table all     # include non-main routing tables
route -n                    # legacy tool, numeric output
```

**Example usage and expected output:**

```bash
$ ip route show
default via 203.0.113.1 dev eth0 proto static metric 100
10.0.1.0/24 dev eth1 proto kernel scope link src 10.0.1.1 metric 100
10.0.2.0/24 via 10.0.1.2 dev eth1 proto static metric 50
10.0.2.15/32 via 10.0.1.2 dev eth1 proto static metric 10
```

**Example usage and expected output (continued — verifying the winning route):**

```bash
$ ip route get 10.0.2.15
10.0.2.15 via 10.0.1.2 dev eth1 src 10.0.1.1
    cache

$ ip route get 10.0.2.99
10.0.2.99 via 10.0.1.2 dev eth1 src 10.0.1.1
    cache
```

**Production usage example:** `ip route get <ip>` is the fastest way to *prove* which route the kernel will actually choose for a given address, sidestepping the need to manually compare prefix lengths by eye across a long routing table — this is the standard first step when a route table has grown large and it's not obvious which entry governs a specific destination.

**Common errors:** Assuming the *lowest metric* route wins overall, without checking prefix length first — a common misreading of output like the example above, where the `/32` route (metric 10, the "best" looking metric) would win for `10.0.2.15` regardless of what metric the `/24` or default route carried, purely because it is more specific.

### 5.2 Reading a Cloud VPC Route Table (AWS Example)

**Purpose:** Show that cloud-provider route tables use the identical longest-prefix-match rule as physical/OS routing tables, just presented in a console/CLI format.

**Syntax:**

```bash
aws ec2 describe-route-tables --route-table-ids <rtb-id>
```

**Example usage and expected output:**

```text
Destination           Target
──────────────────────────────────
10.0.0.0/16            local
10.0.2.0/24            pcx-0abc123 (VPC peering connection)
0.0.0.0/0               igw-0def456 (Internet Gateway)
```

**Production usage example:** For a subnet whose route table looks like this, traffic to `10.0.2.50` (inside `10.0.2.0/24`) is routed across the peering connection rather than following the broader `10.0.0.0/16 local` route, and traffic to `8.8.8.8` falls through to the internet gateway via the default route — exactly longest-prefix-match, just rendered in the AWS console instead of `ip route show`. This exact pattern governs whether a private subnet's traffic egresses through a NAT gateway, a peering connection, or a Transit Gateway attachment ([§104](../Part12/Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)).

**Common errors:** Adding an overly broad route (e.g., a `/16` pointing at a peering connection) that unexpectedly "steals" traffic that was meant to stay local within a more specific but visually buried `/24` local route — always check for the most specific matching prefix, not the route that "looks like" it should apply.

## 6. Production Usage Notes

- **Route table size matters for performance on real hardware but not for correctness.** Large routing tables (internet-scale routers can carry 900,000+ IPv4 routes for full BGP tables) rely on efficient longest-prefix-match data structures (compressed tries) — but the *logical* outcome is identical to the naive "compare every prefix" model in this section's diagram.
- **Overlapping routes are a deliberate and common design pattern, not a mistake.** A broad summary route plus specific exception routes ([§28](Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md)) is a standard technique — the more specific exception always wins by design, which is precisely what makes the pattern work rather than being ambiguous.
- **Cloud route table "most specific route wins" behavior is silent** — there is typically no warning in the console when a newly added specific route overrides traffic flow for a subset of a broader existing route; changes should be reviewed carefully in change management before applying.

## 7. Security Considerations

- A maliciously or accidentally injected more-specific route can silently divert traffic away from its intended path (a form of route hijacking) — because longest-prefix-match always favors specificity, an attacker who can inject even a single `/32` or `/30` route into a routing domain can redirect traffic for that narrow range without touching any broader, "trusted-looking" route.
- Route table changes (physical or cloud) should be treated as security-sensitive configuration, since a single new specific route can redirect sensitive traffic through an unintended path (e.g., away from an encrypted VPN tunnel and out a default internet route) without any other visible configuration change.
- In cloud environments, route table modification permissions should be tightly scoped via IAM — a compromised principal with route-table-write permissions can silently reroute a VPC subnet's traffic to an attacker-controlled peering connection or gateway.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                    | Resolution Path                                                                                                              |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Traffic to one specific IP behaves differently than the rest of its subnet | A more specific route (often a `/32`) exists for that IP and wins over the subnet's broader route   | `ip route get <ip>` (or the cloud console's route table) to identify the actual winning route, not just the subnet's expected route |
| Newly added route doesn't seem to take effect for some destinations       | An existing, more specific route already covers those destinations and continues to win            | Compare prefix lengths of the new route against existing routes covering the same address space; the more specific one always wins  |
| Cloud subnet's traffic unexpectedly transits a peering connection instead of staying local | A specific route to a peered CIDR was added that is more specific than the subnet's local route | Review the route table for any route more specific than the local VPC CIDR; confirm it's intentional |

## 9. Best Practices

- When troubleshooting "why did this packet go there," always identify the actual longest-prefix match first — comparing metrics or reading routes in table order without checking specificity is a common and time-wasting mistake.
- Document any intentionally overlapping routes (a summary route plus specific exceptions) clearly, since a routing table with unexplained overlapping prefixes is difficult for the next engineer to reason about safely.
- Before adding a new route (physical or cloud), check whether an existing more-specific route already governs the destinations you intend to affect — a new route is only in effect if nothing more specific already claims those addresses.

## 10. Common Anti-Patterns / Mistakes

- **Comparing metrics across routes with different prefix lengths as if they compete.** Metric only matters when prefix lengths are equal; a lower-metric `/16` route never beats a higher-metric `/24` covering an overlapping address.
- **Adding a "just in case" broad route without checking what more-specific routes it might shadow or be shadowed by** — leading to routing behavior that looks correct on paper but produces surprising forwarding decisions for specific addresses.
- **Assuming routing table order (as displayed) determines precedence.** Real forwarding engines do not evaluate top-to-bottom; the display order is usually arbitrary (insertion order, alphabetical, or protocol-grouped) and has no bearing on which route wins.

## 11. Interview Questions

**🎯 Beginner:** _"What is the longest-prefix-match rule?"_
**Model answer:** When a router has multiple routes in its table that could match a packet's destination address, it picks the route with the most specific (longest) prefix — the one with the highest subnet mask/prefix length — rather than the route with the lowest metric or the one listed first. A `/32` route always beats a `/24` route to an overlapping address, which always beats a `/0` default route.
_What the interviewer is probing for:_ Whether the candidate knows the single rule that governs all IP forwarding decisions, at a basic conceptual level.

**🎯 Intermediate:** _"Given a routing table with a default route (0.0.0.0/0), a /16 route, and a /24 route that all cover a destination IP, which one does the router use, and why?"_
**Model answer:** The router uses the /24 route, because it's the most specific (longest prefix) match among the three, regardless of each route's metric, administrative distance, or how it was learned (static vs. dynamic). The /16 and the default route both also technically match the destination, but longest-prefix-match means only the most specific matching entry is used; the others are simply not selected for this particular destination.
_What the interviewer is probing for:_ Whether the candidate can apply the rule concretely to a scenario with multiple overlapping matches, not just recite the definition.

**🎯 Senior:** _"A teammate adds a new /32 static route to fix connectivity to one problem host, and afterward a completely unrelated set of hosts in the same /24 starts experiencing intermittent issues. What would you check first?"_
**Model answer:** I'd first confirm the new /32 route's next hop and interface are correct and haven't introduced a routing loop or a path that bypasses something the rest of the /24 depends on (a firewall, a NAT gateway, a monitoring tap). Because the /32 only affects traffic to that one specific address, it shouldn't directly affect the rest of the /24 unless something else changed simultaneously — so I'd also check whether the change process itself (a config push, an automation run) touched anything beyond the intended single route, since longest-prefix-match guarantees the /32 addition is isolated to traffic for that one IP and cannot itself explain broader /24 symptoms.
_What the interviewer is probing for:_ Whether the candidate correctly reasons that longest-prefix-match scopes the blast radius of a route change to only the addresses it actually covers, and doesn't jump to blaming the new route for unrelated symptoms without evidence.

**🎯 Architect:** _"You're designing a hybrid network where an on-prem subnet is summarized as a single /16 route advertised to a cloud VPC, but three /24s within that /16 need to be routed differently (e.g., to a different VPN tunnel or security appliance). How do you achieve this without breaking the summary route for everything else?"_
**Model answer:** I'd rely explicitly on longest-prefix-match: keep the /16 summary route as the default path for the on-prem network, and add three specific /24 static (or dynamically redistributed) routes pointing at the alternate tunnel or appliance. Because those /24s are more specific than the /16 summary, they'll always win for traffic to those subnets while every other address within the /16 continues to use the summary route unaffected — no explicit "exception" mechanism is needed beyond the routing table's native prefix-specificity behavior. I'd document this pattern explicitly, though, since a routing table with a broad summary and narrower carve-outs is easy for a future engineer to misread as redundant or conflicting if the design intent isn't recorded — and I'd validate the design with an `ip route get` (or cloud route-table trace) style check against representative addresses in each /24 to prove the intended path before rollout.
_What the interviewer is probing for:_ Whether the candidate can design a real routing topology that deliberately exploits longest-prefix-match for traffic engineering, and is careful about maintainability/documentation, not just correctness.

## 12. Common Misconceptions

1. **"The route with the lowest metric always wins."** Metric only breaks ties between routes with the *same* prefix length; a longer (more specific) prefix always wins first, regardless of metric.
2. **"Routing table order determines which route is used."** The order routes are displayed in has no bearing on route selection — the forwarding engine always evaluates specificity, not table position.
3. **"A more specific route needs some special 'override' flag to take precedence."** No such flag exists or is needed — specificity alone determines precedence; this is the entire mechanism.
4. **"Cloud route tables work differently from OS/router routing tables."** They implement the identical longest-prefix-match logic; only the presentation (console/CLI vs. `ip route show`) differs.

## 13. 🔑 Key Takeaways

- A routing table is an ordered set of destination-prefix-to-next-hop mappings; the forwarding engine picks the route with the longest (most specific) matching prefix for any given destination.
- Metric and administrative distance only matter for breaking ties between routes with identical prefix length — they never override a more specific match.
- A default route (0.0.0.0/0) is the least specific possible route and is only used when nothing more specific matches.
- Overlapping routes (a broad summary plus specific exceptions) are a valid, common design pattern that relies entirely on longest-prefix-match to work correctly.
- Cloud VPC route tables (AWS, Azure, GCP) implement the exact same longest-prefix-match rule as physical routers and OS routing tables.

## 14. Related Concepts & What's Next

[§25](Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) introduced the router's basic forwarding role that this section formalizes into the table structure and matching rule. [§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md) shows how routes are manually added to this table via static routing. [§28](Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md) builds directly on longest-prefix-match to explain why route summarization (broad routes plus specific exceptions) is safe. [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) returns to administrative distance — only briefly introduced here — in full depth, covering how routes from different sources are ranked when prefix lengths tie. [§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) applies this identical rule to cloud VPC route tables.

**Next Section:** [§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md) — `Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md`
