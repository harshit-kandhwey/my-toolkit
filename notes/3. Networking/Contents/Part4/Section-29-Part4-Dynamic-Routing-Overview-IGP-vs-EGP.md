# Section 29 (Part 4): Dynamic Routing Overview: IGP vs. EGP

## 1. Definition

**Plain language:** Dynamic routing is what happens when routers talk to each other and figure out, automatically, how to reach every network — instead of a human typing in every route by hand. Some of these conversations happen between routers that all belong to the same organization (interior), and some happen between routers representing entirely different organizations that have agreed to exchange traffic with each other (exterior) — and the two situations call for very different kinds of protocols.

**Precise definition:** **Dynamic routing** is the automated discovery, exchange, and maintenance of routing information between routers using a **routing protocol**, so that routing tables adapt automatically to topology changes (a link failing, a new subnet being added) without manual reconfiguration. Dynamic routing protocols fall into two categories based on scope: an **Interior Gateway Protocol (IGP)** operates *within* a single **autonomous system (AS)** — a network (or collection of networks) under one organization's unified administrative control — and is optimized for finding the fastest/best internal path (examples: RIP, [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md); OSPF, [§31](Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md); EIGRP; IS-IS). An **Exterior Gateway Protocol (EGP)** operates *between* different autonomous systems, exchanging reachability information across organizational boundaries where trust, policy, and business relationships matter as much as raw path length — the only EGP in real, current use is **BGP** (Border Gateway Protocol, [§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)), which is the protocol that literally holds the global internet together by exchanging routes between every ISP, cloud provider, and large enterprise network.

> 💡 **Tip:** The IGP/EGP split is not really about the algorithm — it's about **trust boundary**. Inside an AS, all routers are administered by the same team and can be trusted to cooperate honestly, so IGPs optimize purely for the best path. Between autonomous systems, no such trust exists — an ISP has no reason to blindly trust another ISP's claimed "best path," and business/policy considerations (peering agreements, transit costs) often matter more than raw path length. This is why BGP is fundamentally a *policy-based* protocol first and a shortest-path protocol a distant second, while IGPs are the reverse.

## 2. Why This Matters

- **It explains why the internet doesn't use one universal routing protocol.** A single protocol optimized for "shortest path within a trusted network" (an IGP) would be catastrophically exploitable and commercially unworkable across the thousands of independently operated networks that make up the internet — this is precisely the problem BGP as an EGP is designed to solve differently.
- **Every cloud environment runs both categories, even if invisibly.** Inside a large cloud provider's own backbone, an IGP-like protocol manages internal path selection; at the edges, BGP is used both by the cloud provider's own network and increasingly exposed directly to customers (AWS Direct Connect with BGP, Azure ExpressRoute with BGP, [§106](../Part12/Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md)) for hybrid connectivity.
- **Autonomous System Numbers (ASNs) are a real, practical artifact engineers encounter.** Any organization peering directly with an ISP, running BGP for multi-homing, or configuring a cloud hybrid connection needs to understand what an AS is and why it has a number — this section is the conceptual entry point for that.
- **Troubleshooting dynamic routing requires knowing which category is misbehaving.** An OSPF neighbor adjacency failing is an entirely different problem class (and toolkit) from a BGP route not being advertised or accepted — conflating the two wastes significant diagnostic time.
- **Certification and interview relevance.** "What's the difference between an IGP and an EGP, and name one of each" is one of the most commonly asked foundational routing questions across networking and cloud infrastructure interviews.

## 3. Prerequisites and Dependencies

Builds on [§25](Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) through [§28](Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md) (routing fundamentals, routing tables, static routing, and default/summarized routes) — dynamic routing is presented here as the automated alternative to everything manually configured in the preceding three sections. No prior protocol-specific knowledge is assumed; [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md), [§31](Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md), and [§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) build out RIP, OSPF, and BGP respectively at the conceptual depth this roadmap targets. [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) later covers how routes learned from multiple different dynamic protocols (or mixed with static routes) are ranked against each other via administrative distance.

## 4. Architecture / Conceptual Diagram

```text
                    THE INTERNET (many independent Autonomous Systems)

   AS 64512 (Company A)              AS 64513 (ISP)              AS 64514 (Company B)
   ┌─────────────────────┐          ┌──────────────┐          ┌─────────────────────┐
   │  Internal routers    │          │              │          │  Internal routers    │
   │  run an IGP          │◄──BGP───►│  runs BGP    │◄──BGP───►│  run an IGP          │
   │  (OSPF, EIGRP, etc.) │  (EGP)   │  internally  │  (EGP)   │  (OSPF, EIGRP, etc.) │
   │  to find best path   │          │  and toward  │          │  to find best path   │
   │  WITHIN the company   │          │  every peer  │          │  WITHIN the company   │
   └─────────────────────┘          └──────────────┘          └─────────────────────┘
        Trust: full                  Trust: policy-based        Trust: full
        (one administrator)          (many administrators,      (one administrator)
                                       contractual relationships)

   Key distinction:
   - IGP (inside AS 64512, AS 64514): optimizes for shortest/best path.
     All routers trust each other completely — one team configures both ends.
   - EGP / BGP (between AS 64512 ↔ 64513 ↔ 64514): optimizes for POLICY —
     which routes to accept, advertise, and prefer, shaped by business
     agreements (peering, transit contracts) — NOT purely shortest path.
```

- **Autonomous System boundary = trust boundary.** Everything inside one AS runs an IGP because one administrative entity controls the whole thing and can safely optimize purely for path efficiency; everything crossing an AS boundary runs BGP because no such unified trust exists.
- **BGP is the only EGP that survived in practice.** Earlier EGPs (the original "EGP" protocol from the 1980s) existed but were superseded entirely by BGP, which is why "EGP" as a category is functionally synonymous with "BGP" in any modern network.
- **A single organization can, and often does, run both** — an IGP internally to manage its own routers, and BGP at its network edge(s) to exchange routes with ISPs, cloud providers, or partner networks; the two protocols typically exchange information with each other via **redistribution** ([§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)) at the boundary.

## 5. Hands-On

### 5.1 Identifying Which Dynamic Routing Protocols Are Running on a Linux-Based Router

**Purpose:** Show how to inspect which dynamic routing protocol(s) a Linux system (commonly running FRRouting or Bird as a software router) has active, and distinguish IGP-learned routes from static or BGP-learned ones in the routing table.

**Syntax:**

```bash
ip route show                    # shows the 'proto' field indicating route source
vtysh -c "show ip route summary" # FRRouting — summarizes routes by protocol
```

**Example usage and expected output:**

```bash
$ ip route show
default via 203.0.113.1 dev eth0 proto bgp metric 20
10.0.1.0/24 dev eth1 proto ospf metric 10
10.0.2.0/24 via 10.0.1.5 dev eth1 proto ospf metric 20
192.168.100.0/24 via 10.0.1.1 dev eth1 proto static

$ vtysh -c "show ip route summary"
Route Source         Routes               FIB
kernel                1                    1
connected             2                    2
static                1                    1
ospf                  2                    2
bgp                   1                    1
```

**Production usage example:** On any software-based router (common in cloud-native networking, service mesh edge nodes, or self-managed network appliances running FRRouting), confirming which protocol actually installed a given route — visible in the `proto` field — is the first step in scoping a routing issue to the right protocol's diagnostic toolkit (OSPF neighbor state vs. BGP session state, entirely different troubleshooting paths).

**Common errors:** Assuming a route with a low metric is "the IGP route" and a route with a high metric is "the EGP/BGP route" — metrics are not comparable across protocols by convention or default; the `proto` field is the only reliable way to identify a route's source, since administrative distance ([§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)), not raw metric value, is what actually decides between competing sources.

### 5.2 Inspecting an Autonomous System's Public ASN and BGP Presence

**Purpose:** Look up an organization's real, publicly registered Autonomous System Number and confirm it is actively announcing routes — the practical, real-world artifact of the IGP/EGP boundary.

**Syntax:**

```bash
whois -h whois.radb.net AS<asn>
```

**Example usage and expected output:**

```bash
$ whois -h whois.radb.net AS15169
aut-num:    AS15169
as-name:    GOOGLE
descr:      Google LLC
country:    US
```

**Production usage example:** Organizations setting up BGP-based hybrid cloud connectivity (AWS Direct Connect, Azure ExpressRoute, [§106](../Part12/Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md)) must obtain and configure their own public or private ASN as part of establishing the BGP EGP session with the cloud provider's edge — this lookup is a standard step in validating that an ASN is correctly registered before a peering session is established.

**Common errors:** Confusing a **private ASN** (in the reserved ranges 64512-65534 for 16-bit, or a similarly reserved 32-bit range — used for internal/non-internet-facing BGP sessions such as most cloud hybrid connections) with a **public ASN** (globally unique, registered with a Regional Internet Registry, required only if the organization is actually announcing routes to the public internet) — most enterprise hybrid-cloud BGP setups only need a private ASN, not a public one.

## 6. Production Usage Notes

- **Most organizations never need to run BGP with the public internet directly** — they connect to one or more ISPs who handle public internet routing, and only run BGP themselves if they're multi-homed to multiple ISPs, operate their own address space, or connect to a cloud provider via a BGP-based hybrid link.
- **Cloud provider backbones are themselves large autonomous-system-like networks internally optimized with IGP-equivalent mechanisms** — while this is largely invisible to customers, it explains why "traffic within a single cloud region" often takes remarkably direct, low-latency paths compared to the public internet's typically more circuitous BGP-selected routes.
- **IGP choice (OSPF vs. EIGRP vs. IS-IS) is largely an operational/vendor preference within an organization**, while BGP is not optional at all for any network that needs to exchange routes with an external autonomous system — there is no viable EGP alternative in modern practice.

## 7. Security Considerations

- IGPs generally assume a trusted internal network and have comparatively weak built-in protections against a rogue or compromised device injecting false routing information — internal network segmentation and authentication (OSPF/EIGRP support cryptographic neighbor authentication) matter precisely because IGP trust assumptions are strong.
- BGP, despite governing the entire internet's reachability, has historically weak default security — BGP hijacking (an AS falsely announcing routes to address space it doesn't own) has caused real, large-scale internet outages and traffic interception incidents; mitigations like **RPKI** (Resource Public Key Infrastructure) and route filtering are covered at the depth this roadmap targets in [§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md).
- The IGP/EGP trust-boundary distinction is itself a security-relevant concept: any device or link crossing from an IGP-trusted internal zone into BGP/EGP territory is a natural point for route filtering and policy enforcement, since it's exactly where blind trust in "what the neighbor says" must stop.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                     | Resolution Path                                                                                                             |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Internal routes are learned and converge quickly, but hybrid-cloud/external routes are missing | The IGP is functioning correctly, but the BGP session to the external peer (cloud provider, ISP) hasn't established | Check BGP session/neighbor state specifically — an IGP problem and a BGP problem require entirely different diagnostics       |
| A route appears with an unexpectedly high or low administrative distance/metric compared to expectations | The route was learned from a different protocol (IGP vs. static vs. BGP) than assumed, each with its own default AD | Check the route's `proto` field (or platform equivalent) to confirm its actual source before comparing metrics                |
| Two departments' networks, each administered separately, can't cleanly share routing policy | Attempting to treat two genuinely separate administrative domains as if they were a single AS running one IGP | Reconsider the trust boundary — if genuine independent administration exists, an EGP (BGP) relationship, not a shared IGP, is the correct model |

## 9. Best Practices

- Use an IGP for anything genuinely under one administrative domain's control, and reserve BGP for actual organizational/trust boundaries — running BGP purely internally "because it's more powerful" adds policy complexity with no corresponding trust-boundary justification.
- When establishing any BGP relationship (even a private, internal-only one for hybrid cloud connectivity), explicitly plan ASN usage (private vs. public range) and document the peering relationship's intent before configuration, since BGP misconfiguration has an unusually large potential blast radius.
- Keep IGP and EGP diagnostic knowledge separate in team runbooks — "check OSPF neighbor state" and "check BGP session state" are different investigative paths, and a runbook that conflates them slows down incident response.

## 10. Common Anti-Patterns / Mistakes

- **Treating "dynamic routing" as one undifferentiated concept** rather than recognizing the fundamentally different trust models and design goals of IGPs versus BGP — this leads to applying IGP intuitions ("just pick the shortest path") to BGP troubleshooting, where policy, not path length, usually explains the observed behavior.
- **Running BGP where a simple IGP or even static routing would suffice**, adding operational complexity (policy configuration, ASN management, route filtering) without a genuine multi-administrative-domain requirement to justify it.
- **Assuming a public ASN is required for any BGP usage** — most hybrid-cloud and enterprise multi-homing scenarios only need a private ASN, and obtaining/managing a public ASN unnecessarily adds registration and maintenance overhead.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between an IGP and an EGP? Name an example of each."_
**Model answer:** An IGP (Interior Gateway Protocol) operates within a single autonomous system — a network under one organization's administrative control — and is optimized to find the best internal path; OSPF and RIP are examples. An EGP (Exterior Gateway Protocol) operates between different autonomous systems, where trust and business policy matter as much as path length; BGP is the only EGP used in practice today, and it's the protocol that connects every major network on the internet.
_What the interviewer is probing for:_ Whether the candidate has the basic scope distinction (internal vs. between organizations) and can name real protocols in each category.

**🎯 Intermediate:** _"Why can't the internet just use an IGP like OSPF everywhere instead of needing a separate protocol like BGP?"_
**Model answer:** IGPs like OSPF are designed for a trusted environment where all routers are administered by the same organization and can be relied on to report accurate information — they optimize purely for shortest/best path and don't have strong mechanisms for policy control or defending against untrustworthy peers. The internet is made of thousands of independently operated networks with no shared trust and often competing business interests (an ISP won't want to blindly accept "shortest path" claims from a network it has no business relationship with, and needs to enforce peering/transit agreements). BGP is designed specifically for that environment: it's policy-driven first, letting each autonomous system decide what routes to accept, prefer, and advertise based on business rules, not just path length. OSPF's design assumptions (implicit trust, pure shortest-path optimization) simply don't hold at internet scale across independent organizations.
_What the interviewer is probing for:_ Whether the candidate understands the *reason* for the IGP/EGP split (trust and policy, not just "different protocols for different sizes of network"), which is the deeper concept behind the terminology.

**🎯 Senior:** _"A company has two data centers connected by a private WAN link, each running OSPF internally. They're now setting up a direct BGP-based connection to a cloud provider for hybrid connectivity. Do the two data centers' OSPF domains need to become one, and does the cloud connection change that?"_
**Model answer:** No — the two data centers' OSPF domains can remain separate, joined, or bridged depending on the company's own internal design preference (that's an IGP design decision independent of anything external), and the new BGP connection to the cloud provider doesn't force any change there. The cloud provider's network is a separate autonomous system with its own administrative control, so the relationship between the company's network(s) and the cloud provider is correctly modeled as an EGP (BGP) relationship regardless of how the company organizes its internal IGP topology. In practice, the company would run BGP at the edge device(s) connecting to the cloud provider, and use route redistribution ([§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)) to inject routes learned via BGP into the internal OSPF domain(s) (and vice versa, advertising internal routes to the cloud via BGP) — the IGP and EGP layers interoperate at that redistribution boundary but remain conceptually and operationally distinct.
_What the interviewer is probing for:_ Whether the candidate correctly keeps the IGP (internal, trust-based) and EGP (external, policy-based) layers conceptually separate even when they need to interoperate, and understands redistribution as the bridging mechanism rather than assuming the domains must merge.

**🎯 Architect:** _"You're designing network connectivity for a company acquiring several smaller companies, each with existing internal OSPF networks and each planning to connect to the parent company's network and to shared cloud infrastructure. How do you approach integrating routing across these organizationally distinct networks?"_
**Model answer:** I would treat each acquired company's network as its own autonomous system boundary rather than trying to merge their internal OSPF domains directly into the parent's — that preserves each network's existing internal design, minimizes disruptive renumbering/re-architecture during the acquisition period, and correctly reflects that (at least initially, and possibly permanently for larger or slower-integrating acquisitions) these remain administratively distinct networks. I'd establish BGP (with private ASNs for each) as the EGP layer connecting each acquired company's network to the parent's core network and to shared cloud infrastructure, using route redistribution at each boundary to selectively expose only the necessary internal routes rather than flooding full internal topology information across organizational lines. This also gives me a natural point to apply route filtering and policy (which acquired company can reach which shared resources, and under what conditions) exactly at the BGP boundary — something that would be much harder to enforce cleanly if everything were merged into one flat internal IGP domain. Over time, for acquisitions that are fully integrated organizationally, the internal OSPF domains could be consolidated as a separate, later decision — but I'd default to keeping the trust/policy boundary (BGP between ASes) in place from day one rather than assuming immediate full network integration.
_What the interviewer is probing for:_ Whether the candidate can apply the IGP/EGP trust-boundary concept to a realistic, messy organizational scenario (M&A network integration) and use BGP's policy capabilities deliberately, rather than defaulting to "just merge everything into one big network."

## 12. Common Misconceptions

1. **"Dynamic routing protocols are interchangeable — pick whichever one is easiest to configure."** IGPs and BGP solve fundamentally different problems (internal path optimization vs. cross-organizational policy); the choice is dictated by whether a genuine trust/administrative boundary exists, not ease of configuration.
2. **"BGP always picks the shortest or fastest path, like an IGP does."** BGP's best-path selection is policy-driven first (local preference, AS-path length as a tiebreaker among other factors) — a BGP-selected path is frequently not the geographically or technically shortest one, because business policy overrides pure path-length optimization.
3. **"You need a public ASN to use BGP at all."** Most enterprise and hybrid-cloud BGP usage uses private ASNs (reserved ranges) and never touches the public internet's routing tables directly.
4. **"An organization only ever needs one type of routing protocol."** It's entirely normal, and common, for an organization to run an IGP internally and BGP at its edge(s) simultaneously, with redistribution bridging the two.

## 13. 🔑 Key Takeaways

- Dynamic routing automates route discovery and adaptation; it splits into IGPs (within one autonomous system, optimized for best internal path, trust-assuming) and EGPs (between autonomous systems, policy-driven, trust-agnostic).
- BGP is the only EGP in practical modern use — it is the protocol that connects every independently operated network on the internet, including cloud providers.
- The IGP/EGP boundary is fundamentally about administrative trust, not network size or geography — a small network spanning one trust domain still only needs an IGP; two large networks under different administrative control need BGP between them regardless of size.
- Organizations commonly run both an IGP internally and BGP at their network edge simultaneously, bridged via route redistribution ([§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md)).
- Most enterprise/hybrid-cloud BGP usage relies on private ASNs and never needs to interact with the public internet's global routing table directly.

## 14. Related Concepts & What's Next

[§25](Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) through [§28](Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md) established the routing fundamentals and manual (static) routing patterns that dynamic routing automates. [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md) covers RIP as an early, simple distance-vector IGP example. [§31](Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md) covers OSPF as the modern link-state IGP most commonly encountered in enterprise and data center networks. [§32](Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) covers BGP in depth as the sole practical EGP and the protocol underlying internet-wide and cloud hybrid connectivity. [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) covers route redistribution, the mechanism that bridges IGP and EGP domains, along with administrative distance for ranking routes from different sources. [§106](../Part12/Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md) revisits BGP specifically in the context of cloud hybrid connectivity (Direct Connect, ExpressRoute).

**Next Section:** [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md) — `Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md`
