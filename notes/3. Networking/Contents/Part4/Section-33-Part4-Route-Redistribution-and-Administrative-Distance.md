# Section 33 (Part 4): Route Redistribution and Administrative Distance

## 1. Definition

**Plain language:** Real networks rarely run just one routing protocol everywhere — a company might run OSPF internally, BGP at its internet edge, and have a handful of static routes for good measure. Route redistribution is how information learned by one protocol gets shared into another, so the whole network has a consistent view. Administrative distance is the tiebreaker rule a router uses when it learns about the *exact same destination* from two different sources — "if OSPF and a static route both claim to know how to reach 10.0.5.0/24, which one do I actually believe?"

**Precise definition:** **Route redistribution** is the explicit configuration action of taking routes learned by one routing protocol (or a set of static routes) and re-advertising them into a different routing protocol's domain, translating between each protocol's native metric system in the process (since a redistributed route needs *some* metric value in its new protocol, and there's no universal conversion between, say, OSPF cost and RIP hop count — the administrator typically assigns a default "seed metric" for redistributed routes). **Administrative distance (AD)** is a per-source trustworthiness ranking — a single integer value, ranging by convention from 0 (most trusted) to 255 (never trust/unusable) — that a router uses to select among multiple routes to the *identical destination prefix* learned from *different sources*, evaluated only when longest-prefix-match ([§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)) alone cannot decide because the competing routes share the exact same prefix length. Typical default administrative distances (values vary slightly by vendor, but the relative ordering is consistent across virtually all platforms): a directly connected interface (0), a static route (1), eBGP (20), OSPF (110), RIP (120), and iBGP (200) — meaning a router will always prefer a static route over an OSPF route to the identical prefix by default, purely because of AD, regardless of either route's own metric.

> 💡 **Tip:** Administrative distance and a protocol's own internal metric (OSPF cost, RIP hop count, BGP's best-path attributes) operate at completely different stages of the decision process and must never be confused. Administrative distance decides *which protocol's answer to trust* when multiple protocols claim the same destination; a protocol's own metric only matters for choosing the best path *among routes learned by that same protocol*. A route redistributed from OSPF into RIP doesn't carry its OSPF cost forward into RIP's hop-count world — it gets a fresh, administrator-assigned seed metric in RIP's own units, because the two numbers describe fundamentally incompatible things.

## 2. Why This Matters

- **Almost every real production network runs more than one routing "source"** — static routes, one or more IGPs, and BGP at the edge — and understanding how these interact (which one "wins" for a given prefix) is essential to correctly reading and predicting real routing table behavior.
- **Redistribution is a common and hazardous operational task.** Misconfigured redistribution (particularly *mutual* redistribution between two protocols at more than one boundary point) is one of the most well-documented ways to accidentally create a routing loop in an otherwise correctly designed network — this section's failure-mode discussion is directly relevant to real production incidents.
- **Administrative distance explains routing table entries that otherwise look wrong.** An engineer who sees a static route "winning" over what looks like a better dynamically learned OSPF path, with no obvious reason, needs to know AD exists and check it before assuming a bug or misconfiguration.
- **Cloud hybrid connectivity always involves an implicit redistribution/AD decision.** When on-premises routes arrive via BGP over Direct Connect/ExpressRoute alongside statically configured VPN routes to the same destinations, the receiving router (physical or cloud-native) applies the exact AD logic covered here to decide which path wins.
- **It's a frequently tested senior-level concept** because getting it right requires synthesizing several earlier sections (longest-prefix-match, multiple protocols, metrics) rather than recalling an isolated fact.

## 3. Prerequisites and Dependencies

Builds directly on [§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) (routing tables and longest-prefix-match — AD only applies once prefix length is tied), [§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md) (static routing, which carries a specific default AD), [§29](Section-29-Part4-Dynamic-Routing-Overview-IGP-vs-EGP.md) (dynamic routing overview), [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md) (RIP), [§31](Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md) (OSPF), and [§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) (BGP) — this section is the synthesis point where all of Part 4's routing sources are compared against each other for the first time. [§34](Section-34-Part4-Policy-Based-Routing-and-Route-Metrics.md) follows, covering policy-based routing and metrics as additional path-selection tools that operate independently of AD.

## 4. Architecture / Conceptual Diagram

```text
   ADMINISTRATIVE DISTANCE — deciding BETWEEN SOURCES for the SAME prefix

   Router R1 learns about 10.0.5.0/24 from THREE different sources:

   Source              AD    Metric        Prefix Length
   ───────────────────────────────────────────────────────
   Static route         1    n/a           /24
   OSPF                110    cost 20      /24
   RIP                 120    3 hops       /24

   All three claim the IDENTICAL /24 prefix — longest-prefix-match
   (§26) can't decide, since prefix length is tied across all three.
   → Administrative Distance breaks the tie: LOWEST AD WINS.
   → Static route (AD 1) is installed. OSPF and RIP's routes for this
     exact prefix are NOT installed (though still tracked internally
     by their respective protocols in case the static route is removed).

   If the static route is later removed:
   → OSPF (AD 110) now wins over RIP (AD 120) for the same prefix.

   Only if the static route AND OSPF's route to 10.0.5.0/24 both
   disappear does RIP's route (AD 120) finally get installed.


   REDISTRIBUTION — translating routes BETWEEN protocol domains

        ┌────────────┐   redistribute    ┌────────────┐
        │    OSPF     │ ────────────────► │    RIP      │
        │  domain     │  (assign a seed   │  domain     │
        │             │   metric in RIP's  │             │
        │             │   own units — RIP  │             │
        │             │   has NO concept   │             │
        │             │   of "OSPF cost")  │             │
        └────────────┘                    └────────────┘

   DANGER — MUTUAL REDISTRIBUTION AT TWO BOUNDARY POINTS creates a
   routing loop risk:

        ┌──────── OSPF ────────┐        ┌──────── RIP ────────┐
        │                       │        │                      │
        │     Router A ─────────┼───────►│    Router B          │
        │        ▲               redistribute    │              │
        │        │              OSPF→RIP here     │              │
        │        │                       │        ▼              │
        │     Router C ◄─────────┼────────────── Router D        │
        │            redistribute RIP→OSPF here                  │
        └───────────────────────┘        └──────────────────────┘

   A route originated in OSPF gets redistributed into RIP at Router B,
   travels through the RIP domain, and gets redistributed BACK into
   OSPF at Router D — potentially re-entering the OSPF domain as if it
   were a "new" external route, creating a loop or a suboptimal/
   incorrect path unless route filtering or tagging explicitly
   prevents re-redistribution of routes that originated on the other side.
```

- **AD is evaluated per-prefix, only among routes that are otherwise tied on specificity** — it never overrides a more specific route from a less-trusted source; a RIP-learned `/25` still beats a static `/24` for an address within that `/25`, because longest-prefix-match ([§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)) is checked first, always.
- **A protocol's own metric is invisible to a different protocol** — redistribution requires an explicit, administrator-chosen "seed metric" precisely because there's no automatic conversion between, say, OSPF cost units and RIP hop counts; this is a deliberate configuration step, not something the router infers.
- **Mutual redistribution at multiple boundary points is the single most common real-world redistribution hazard** — a route can loop back into its own domain of origin, appearing "new" to a protocol that doesn't inherently recognize it came from itself, unless explicit safeguards (route tagging, filtering, or a single deliberate redistribution point) are in place.

## 5. Hands-On

### 5.1 Observing Administrative Distance Resolve a Multi-Source Conflict

**Purpose:** Directly demonstrate AD deciding between a static route and a dynamically learned route to the identical prefix.

**Syntax:**

```bash
ip route show
ip route add 10.0.5.0/24 via 10.0.1.9 dev eth0    # add a static route to a prefix OSPF already knows
```

**Example usage and expected output:**

```bash
$ ip route show | grep 10.0.5.0
10.0.5.0/24 via 10.0.1.5 dev eth1 proto ospf metric 20

$ ip route add 10.0.5.0/24 via 10.0.1.9 dev eth0

$ ip route show | grep 10.0.5.0
10.0.5.0/24 via 10.0.1.9 dev eth0    # static route now installed instead

$ ip route del 10.0.5.0/24 via 10.0.1.9 dev eth0

$ ip route show | grep 10.0.5.0
10.0.5.0/24 via 10.0.1.5 dev eth1 proto ospf metric 20    # OSPF's route reappears
```

**Production usage example:** This exact behavior is why a single manually added static route — sometimes added years earlier for a now-forgotten troubleshooting reason — can silently override an entire dynamic routing protocol's calculated best path for a prefix, and why "audit for stray static routes" is a standard step when a dynamically routed network exhibits unexplained, static-looking behavior for one specific destination.

**Common errors:** Assuming that removing the *dynamic* route (e.g., disabling OSPF for that network) is necessary to "let the static route take effect" — the static route was already winning the whole time due to its lower AD; the OSPF route was simply present in OSPF's own database without being the one actually installed in the forwarding table.

### 5.2 Configuring Route Redistribution with a Seed Metric

**Purpose:** Show the explicit configuration step required to redistribute routes from one protocol into another, including the mandatory seed metric.

**Syntax (FRRouting-style, representative — conceptual depth for this roadmap):**

```text
router rip
 redistribute ospf metric 2
router ospf
 redistribute static metric 20 metric-type 1
```

**Example usage and expected output:**

```text
Router# show ip route rip
R    10.0.5.0/24 [120/2] via 0.0.0.0, redistributed
     ...(originally an OSPF route, now visible in RIP with seed metric 2)

Router# show ip route ospf
O E1 192.168.100.0/24 [110/20] via 0.0.0.0, redistributed
     ...(originally a static route, now visible in OSPF as an
         "external type 1" route with the configured seed metric)
```

**Production usage example:** A common real pattern: a company's OSPF-routed data center network needs reachability to a small set of statically routed legacy subnets — `redistribute static` into OSPF (with an appropriate metric) lets every OSPF-speaking router learn those static routes automatically instead of requiring the same static routes to be manually configured on every single OSPF router individually.

**Common errors:** Omitting the seed metric (relying on a platform default) without understanding what that default actually is — on many platforms, a default redistribution metric of a very low or very high value can cause redistributed routes to be either implausibly preferred or effectively unreachable/unused within the receiving protocol's own path-selection logic, producing confusing behavior that traces back to an unconsidered default rather than an intentional decision.

### 5.3 Diagnosing a Redistribution Loop with Route Tags

**Purpose:** Show how route tagging prevents the mutual-redistribution loop hazard described in this section's diagram.

**Syntax:**

```text
router ospf
 redistribute rip metric 20 route-map TAG-FROM-RIP
route-map TAG-FROM-RIP permit 10
 set tag 100
!
router rip
 redistribute ospf metric 2 route-map BLOCK-IF-TAGGED
route-map BLOCK-IF-TAGGED deny 10
 match tag 100
route-map BLOCK-IF-TAGGED permit 20
```

**Example usage and expected output:**

```text
Router# show ip route ospf | include tag
O E2 10.0.9.0/24 [110/20] via 0.0.0.0, tag 100, redistributed
```

**Production usage example:** At each redistribution boundary in a network with more than one such boundary between the same two protocols, tagging routes at the point of origin (e.g., "this route came from RIP" gets tag 100 when redistributed into OSPF) and filtering on that tag at every *other* redistribution point (refusing to redistribute anything already tagged 100 back into RIP) is the standard, deliberate safeguard against the mutual-redistribution loop scenario — without it, a network with multiple redistribution boundaries between the same two protocols is structurally at risk regardless of how careful the rest of the configuration is.

**Common errors:** Setting up mutual redistribution at exactly one boundary point and assuming this is inherently safe without tagging — a single boundary point is genuinely lower-risk than multiple boundary points, but redistribution safety should still be deliberately verified (via tagging or filtering) rather than assumed safe purely because there's "only one" redistribution point today, since networks grow additional boundary points over time.

## 6. Production Usage Notes

- **Redistribution is a deliberate architectural decision, not a default or automatic behavior on any platform** — routes never cross from one protocol's domain into another's without explicit `redistribute` configuration, which is itself a safeguard (an administrator has to consciously opt in).
- **Administrative distance can be manually overridden per-route or per-source on most platforms** — this is a legitimate advanced technique (e.g., temporarily raising a static route's AD above a dynamic protocol's so the dynamic route is preferred unless it disappears, giving the static route a "floating" backup role) but should be documented clearly, since it inverts the platform's normal default expectations.
- **Cloud hybrid connectivity route tables effectively perform AD-like source-preference decisions**, even though the concept isn't always exposed with the exact term "administrative distance" — when a VPC route table has both a static route and a BGP-propagated route (via Transit Gateway) to overlapping destinations, the platform applies its own defined precedence rules, conceptually identical to AD even if the terminology differs.

## 7. Security Considerations

- Uncontrolled redistribution can leak internal routing detail across a trust boundary that was never intended to see it — redistributing an entire internal IGP's routes into BGP without filtering, for instance, can advertise internal topology information to external peers that should never have visibility into it.
- A redistribution loop (from unfiltered mutual redistribution) is not just a performance problem — during the period a loop exists, affected traffic can be silently dropped or delayed, which itself can be a meaningful availability/security incident depending on what traffic is affected.
- Manually overriding administrative distance to force a specific route's preference is a powerful tool that, if undocumented, can be exploited (or simply mistaken) as a hidden backdoor path — any AD override should be treated as sensitive configuration subject to the same review rigor as an ACL or firewall rule change.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                                          | Resolution Path                                                                                                              |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| A dynamically learned route to a prefix never appears in the routing table, despite the protocol clearly knowing about it | A different source (often a forgotten static route) with a lower administrative distance is winning for the identical prefix | Check for a static or lower-AD route to the exact same prefix; `show ip route <prefix>` (or platform equivalent) to see all candidate sources |
| Intermittent routing loops or flapping routes appear after enabling redistribution between two protocols at more than one point | Mutual redistribution without route tagging/filtering, allowing a route to loop back into its domain of origin | Implement route tagging at each redistribution point and filter on tags to prevent re-redistribution of routes back into their source domain |
| A redistributed route behaves unexpectedly (too preferred, or effectively unreachable) within its new protocol | No explicit seed metric was configured, and the platform default metric for redistributed routes doesn't fit the intended path preference | Explicitly configure an appropriate seed metric for the redistribution rather than relying on platform defaults               |

## 9. Best Practices

- Treat every redistribution point as an explicit, documented architectural decision — note which protocols are involved, the seed metric chosen and why, and any route filtering/tagging applied, since redistribution configuration is easy to forget the reasoning behind years later.
- Default to a single redistribution point between any two protocols wherever the topology allows it; if multiple points are genuinely necessary, implement route tagging from day one rather than waiting for a loop incident to force the issue.
- When troubleshooting "why is this route not what I expect," always check administrative distance and competing sources before assuming a bug in the winning protocol's own metric calculation — a lower-AD source silently overriding an expected dynamic route is one of the most common and easily overlooked explanations.

## 10. Common Anti-Patterns / Mistakes

- **Enabling mutual redistribution between two protocols at multiple boundary points with no route tagging or filtering**, creating exactly the loop-risk scenario this section's diagram illustrates, often discovered only during an actual incident rather than caught in design review.
- **Forgetting that a forgotten static route silently overrides dynamic routing for a specific prefix** due to its default low AD, then spending significant troubleshooting time investigating the dynamic protocol's own (correctly functioning) behavior instead.
- **Manually overriding administrative distance without documentation**, leaving a future engineer to discover an unexpected route preference with no recorded rationale for why it deviates from platform defaults.

## 11. Interview Questions

**🎯 Beginner:** _"What is administrative distance, and why does it exist?"_
**Model answer:** Administrative distance is a trustworthiness ranking a router assigns to each source of routing information — directly connected, static, or a specific dynamic protocol like OSPF, RIP, or BGP. It exists because a router might learn about the exact same destination network from more than one source simultaneously, and needs a consistent rule for deciding which source to actually trust and install into the routing table; lower administrative distance values are more trusted, and the lowest-AD source wins when multiple sources claim the identical prefix.
_What the interviewer is probing for:_ Basic understanding of what problem AD solves — a multi-source conflict for the same destination — rather than just reciting default AD numbers.

**🎯 Intermediate:** _"A router has a static route and an OSPF-learned route to the same /24 prefix. Which one is installed in the routing table, and why?"_
**Model answer:** The static route is installed, because static routes have a default administrative distance of 1, while OSPF's default administrative distance is 110 — lower AD wins. This has nothing to do with either route's own metric (the static route doesn't even really have a comparable "metric" in the OSPF-cost sense); administrative distance is purely a per-source trust ranking used specifically to break ties when longest-prefix-match alone can't decide because the competing routes have identical prefix length.
_What the interviewer is probing for:_ Whether the candidate correctly separates AD (cross-source comparison) from a protocol's own internal metric (within-source comparison), and knows the relative default values well enough to reason about a concrete scenario.

**🎯 Senior:** _"Explain why mutual redistribution between two routing protocols at more than one boundary point is a known risk, and how you'd mitigate it."_
**Model answer:** When two protocol domains are connected by redistribution at more than one point, a route originating in one domain can be redistributed into the other, travel across that second domain, and then get redistributed back into its domain of origin at a different boundary router — appearing to that original domain as if it were a new, externally learned route, since neither redistribution point inherently knows the route already originated on the other side. This can create a routing loop, or at minimum cause a route to be learned via a suboptimal or logically incorrect path back into its own domain. The standard mitigation is route tagging: at each point routes are redistributed out of a domain, tag them with a value identifying their origin, and at every other redistribution point (where routes might flow back in the opposite direction), filter out and refuse to redistribute anything already carrying that origin tag — this cleanly breaks the loop by making each domain aware of which routes are "not really new" regardless of how many redistribution points exist between the two protocols.
_What the interviewer is probing for:_ Whether the candidate can explain the actual mechanism of the redistribution loop risk (not just that it exists) and name the standard, specific mitigation (route tagging) rather than a vague "be careful" answer.

**🎯 Architect:** _"You're integrating a newly acquired company's OSPF network with your organization's existing BGP-based internal backbone, which also needs continued connectivity to a legacy RIP segment neither team wants to migrate immediately. How do you sequence and control the redistribution across three protocols without creating cross-domain routing hazards?"_
**Model answer:** I'd design this with explicit, single, well-documented redistribution boundaries between each pair of protocols rather than allowing ad hoc multiple crossing points to emerge organically as integration work proceeds — specifically: one designated boundary router (or small set) handling OSPF-to-BGP redistribution for the acquired company's routes, and a separate designated boundary handling RIP-to-(whichever internal IGP or BGP)-redistribution for the legacy segment, each with route tagging applied consistently across all three domains from day one, since with three protocols involved the potential redistribution-loop topology is more complex than the two-protocol case and tagging discipline matters even more. I'd also assign explicit, intentional seed metrics at each redistribution point based on real link/path characteristics rather than platform defaults, since with three protocols in play, an unconsidered default metric at any one boundary can produce a globally suboptimal path that's hard to trace back to its actual cause later. Administrative distance would need explicit review too — I'd confirm that no unintended AD relationship between the newly connected domains causes, for example, a legacy RIP route (AD 120) to unexpectedly beat a redistributed OSPF route re-injected into the same domain if their advertised prefixes ever overlap during the transition period. Finally, I'd treat this integration as a phased rollout with the routing changes validated at each step (using `show ip route` comparisons against an expected baseline) rather than activating all three protocols' interconnection simultaneously — a three-protocol redistribution topology has enough combinatorial complexity that incremental validation meaningfully reduces the risk of an undiagnosed loop or blackhole during the cutover itself.
_What the interviewer is probing for:_ Whether the candidate can reason about redistribution risk scaling with the number of protocols/boundaries involved (not just the two-protocol textbook case), and proposes concrete, disciplined mitigations (single designated boundaries, consistent tagging, deliberate metrics, phased validation) appropriate to real organizational integration complexity.

## 12. Common Misconceptions

1. **"Administrative distance and a protocol's metric are the same kind of number, just used differently."** They answer entirely different questions — AD decides which *source* to trust when multiple protocols claim the same prefix; a protocol's own metric decides the best path *among routes from that same protocol* — and they're never directly compared to each other.
2. **"A lower metric always means a route is preferred over a route with a higher administrative distance."** AD is checked first (after longest-prefix-match); a route with the "better looking" metric from a higher-AD (less trusted) source loses to a lower-AD source's route to the identical prefix regardless of metric.
3. **"Redistribution automatically translates a route's metric correctly between protocols."** There is no automatic conversion — redistribution requires an administrator to explicitly assign a seed metric in the target protocol's own units, since the two protocols' metrics are fundamentally incompatible units of measurement.
4. **"Mutual redistribution between two protocols is inherently unsafe and should never be done."** It's safe and common at a single, well-controlled boundary point; the specific hazard is *multiple* uncontrolled boundary points without route tagging/filtering, not mutual redistribution in general.

## 13. 🔑 Key Takeaways

- Route redistribution explicitly shares routing information learned by one protocol into a different protocol's domain, requiring an administrator-assigned seed metric since protocols' native metrics aren't automatically comparable or convertible.
- Administrative distance is a per-source trust ranking used to decide between multiple sources claiming the identical destination prefix — it's evaluated only after longest-prefix-match ([§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)) fails to decide via prefix specificity alone.
- Typical default administrative distances, lowest (most trusted) to higher: directly connected (0), static (1), eBGP (20), OSPF (110), RIP (120), iBGP (200) — the specific relative ordering matters more than memorizing exact numbers.
- Mutual redistribution between two protocols at multiple uncontrolled boundary points is a well-documented routing-loop risk, mitigated by route tagging and filtering at each redistribution point.
- Real production networks routinely combine static routes, one or more IGPs, and BGP simultaneously — understanding how AD and redistribution govern their interaction is essential to correctly predicting and troubleshooting actual routing table behavior.

## 14. Related Concepts & What's Next

[§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) supplied the longest-prefix-match rule that AD only supplements, never overrides. [§27](Section-27-Part4-Static-Routing-Configuration-Patterns-and-Use-Cases.md), [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md), [§31](Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md), and [§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) covered the individual routing sources (static, RIP, OSPF, BGP) whose interaction this section synthesizes. [§34](Section-34-Part4-Policy-Based-Routing-and-Route-Metrics.md) continues into policy-based routing and metrics as additional path-selection tools that operate alongside, but conceptually separate from, administrative distance. [§106](../Part12/Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md) revisits redistribution and AD-like precedence concepts specifically in the context of cloud hybrid connectivity, where BGP-propagated and statically configured routes commonly coexist.

**Next Section:** [§34](Section-34-Part4-Policy-Based-Routing-and-Route-Metrics.md) — `Section-34-Part4-Policy-Based-Routing-and-Route-Metrics.md`
