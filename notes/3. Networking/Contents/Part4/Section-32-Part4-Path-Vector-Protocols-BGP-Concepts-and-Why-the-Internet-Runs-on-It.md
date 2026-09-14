# Section 32 (Part 4): Path-Vector Protocols: BGP Concepts and Why the Internet Runs on It

## 1. Definition

**Plain language:** BGP is the protocol that lets independently run networks — your ISP, a cloud provider, another company entirely — tell each other "here's how to reach the address space I'm responsible for, and here's the list of networks a packet would cross to get there." It's the only protocol trusted enough, and flexible enough on policy, to hold together a network of networks owned by thousands of parties who don't fully trust each other. The internet, mechanically, is the sum of everyone running BGP and agreeing (loosely) to honor each other's advertisements.

**Precise definition:** **BGP** (Border Gateway Protocol, currently **BGP-4**) is a **path-vector** exterior gateway protocol — each route advertisement carries not just a destination prefix and next hop, but an explicit **AS-path**: the ordered list of every Autonomous System a route has traversed. This AS-path serves two purposes simultaneously: a built-in **loop-prevention mechanism** (a router receiving an advertisement that already contains its own AS number in the path rejects it outright, since accepting it would create a loop), and a *rough* tie-breaking metric (shorter AS-path is generally, but not always, preferred). BGP runs as **eBGP** (external BGP) between routers in *different* autonomous systems, and **iBGP** (internal BGP) between routers *within* the same AS that need to carry externally learned routes across their own network. Unlike an IGP, BGP's route selection is **policy-driven**: a lengthy, well-defined **best-path selection algorithm** considers factors including (in rough priority order on most implementations) highest **Weight** (Cisco-proprietary, local significance only), highest **Local Preference** (an AS's own stated preference among multiple exit paths), shortest **AS-path length**, lowest **origin type**, lowest **Multi-Exit Discriminator (MED)**, and eBGP-over-iBGP preference — with raw path length being just one of many factors, and often not the deciding one. BGP peers exchange routes over persistent **TCP port 179** sessions, and BGP itself carries no native encryption — session integrity typically relies on **TCP MD5 signatures** or, increasingly, the newer **TCP-AO** option.

> 💡 **Tip:** The single fact that reframes almost every BGP behavior an engineer finds surprising: BGP optimizes for *policy*, not shortest path, and there is no requirement that any two autonomous systems agree on what "best" means. An AS can — and routinely does — prefer a longer AS-path over a shorter one because of a peering cost agreement, a traffic-engineering decision, or a customer relationship. Anyone approaching BGP with an IGP mindset ("surely it just picks the fastest route") will misdiagnose real BGP behavior constantly; the correct question is always "what does this AS's local policy say," not "what's actually shortest."

## 2. Why This Matters

- **BGP is the protocol the entire public internet runs on.** Every route between every independently operated network on the internet — every ISP, every cloud provider, every large enterprise with its own address space — is exchanged and selected via BGP; there is no alternative in production use.
- **Cloud hybrid connectivity is built directly on BGP.** AWS Direct Connect, Azure ExpressRoute, and GCP Cloud Interconnect all use BGP to dynamically exchange routes between an organization's on-premises network and their cloud VPC/VNet — any infrastructure engineer working on hybrid connectivity will directly configure or troubleshoot BGP sessions.
- **BGP hijacks and route leaks are real, headline-making internet outages.** Misconfigured or malicious BGP announcements have taken down major services and rerouted traffic through unintended (sometimes hostile) networks — understanding BGP's trust model explains why these incidents are possible and what mitigations (RPKI, route filtering) exist.
- **BGP's policy-first design directly explains observed internet behavior** that would otherwise seem arbitrary — why traffic sometimes takes a geographically illogical path, why two ISPs peering directly can still route traffic through a third party, and why "shortest AS-path" is a tiebreaker, not the primary decision factor.
- **Certification and senior-interview relevance.** BGP concepts (AS-path, eBGP vs. iBGP, best-path selection factors) are consistently tested at senior/architect level across cloud and networking interviews, since genuine understanding (versus rote memorization) is hard to fake.

## 3. Prerequisites and Dependencies

Builds directly on [§29](Section-29-Part4-Dynamic-Routing-Overview-IGP-vs-EGP.md) (dynamic routing overview, IGP vs. EGP — BGP is the sole practical EGP discussed there) and benefits from contrast against [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md) (RIP, distance-vector) and [§31](Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md) (OSPF, link-state), since path-vector is a genuinely distinct third category worth comparing against both. [§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)'s longest-prefix-match remains the underlying rule for how BGP-learned routes are ultimately selected for forwarding once BGP's own best-path algorithm has chosen a preferred route among candidates for the same prefix. [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) immediately follows, covering redistribution between BGP and IGPs, and administrative distance for ranking BGP routes against others. [§106](../Part12/Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md) revisits BGP specifically for cloud hybrid connectivity (Direct Connect, ExpressRoute) in more depth.

## 4. Architecture / Conceptual Diagram

```text
   PATH-VECTOR (BGP) — routes carry the FULL LIST of ASes traversed

   AS 64512 (Company)        AS 64513 (ISP A)        AS 64514 (ISP B)
   ┌──────────────┐  eBGP   ┌──────────────┐  eBGP  ┌──────────────┐
   │ 10.0.0.0/16  │────────►│              │───────►│              │
   │ advertises   │         │  Advertises: │        │  Receives:   │
   │ 10.0.0.0/16  │         │  10.0.0.0/16 │        │  10.0.0.0/16 │
   │              │         │  AS-PATH:    │        │  AS-PATH:    │
   └──────────────┘         │  [64512]     │        │  [64513,     │
                             └──────────────┘        │   64512]     │
                                                      └──────────────┘

   AS 64514's router sees AS-PATH [64513, 64512] for 10.0.0.0/16 —
   this tells it EXACTLY which ASes a packet crosses to reach that
   prefix. If AS 64514 also learns the SAME prefix via a different
   path with AS-PATH [64515, 64516, 64512] (3 hops vs. 2), shorter
   AS-path is a FACTOR in preference — but only after Weight and
   Local Preference are checked first; a business policy (Local
   Preference favoring a specific paid transit provider, say) can
   still make AS 64514 choose the LONGER path deliberately.

   LOOP PREVENTION (built into the AS-path itself):
   If AS 64512 ever receives back an advertisement for 10.0.0.0/16
   whose AS-PATH already contains 64512 anywhere in the list, it
   REJECTS it outright — the presence of its own AS number in the
   path is proof accepting it would create a loop. No separate
   loop-detection algorithm is needed; the AS-path itself IS the
   loop-prevention mechanism.

   eBGP vs. iBGP:
   ┌───────────────────── AS 64512 ─────────────────────┐
   │  Edge Router A ◄──iBGP──► Edge Router B              │
   │       ▲                        ▲                    │
   │      eBGP                     eBGP                  │
   │       │                        │                     │
   └───────┼────────────────────────┼─────────────────────┘
          AS 64513                AS 64514
   (Edge Router A learns external routes via eBGP from AS 64513,
    then must relay them via iBGP to Edge Router B so THAT router
    also knows about them — iBGP exists specifically to carry
    externally learned routes across the AS's own internal network.)
```

- **The AS-path is simultaneously data and mechanism** — it's both the information used for policy decisions (shorter/longer path preference) and the loop-prevention mechanism itself, a genuinely elegant dual-purpose design distinct from anything in RIP or OSPF.
- **eBGP and iBGP solve different problems**: eBGP exchanges routes *between* autonomous systems at their boundary; iBGP propagates those externally learned routes *across* a single AS's own internal network so every edge router within that AS has consistent visibility, without which only the router that directly learned an external route would know about it.
- **Best-path selection is a long, ordered list of tie-breaking criteria**, with AS-path length just one entry roughly in the middle of that list — Weight and Local Preference, both purely local policy settings with no relationship to actual path length, are checked first on most implementations, which is precisely why "shortest AS-path always wins" is a common but incorrect simplification.

## 5. Hands-On

### 5.1 Inspecting a BGP Session and Its State

**Purpose:** Confirm whether a BGP peering session has successfully established and is actively exchanging routes — the prerequisite for any route advertisement/reception to matter.

**Syntax:**

```text
show ip bgp summary
show ip bgp neighbors <neighbor-ip>
```

**Example usage and expected output:**

```text
Router# show ip bgp summary
BGP router identifier 10.0.1.1, local AS number 64512
Neighbor        V    AS  MsgRcvd  MsgSent  Up/Down   State/PfxRcd
203.0.113.1     4  64513     8842     8901  3d02h            412
198.51.100.1    4  64514        3        2  00:00:12  Active

Router# show ip bgp neighbors 198.51.100.1
BGP neighbor is 198.51.100.1, remote AS 64514
  BGP state = Active, table version 0
```

**Production usage example:** `State/PfxRcd` showing a numeric value (like `412` above) confirms an `Established` session actively receiving that many prefixes — while a state word instead of a number (`Active`, `Idle`, `Connect`) indicates the session has never successfully established; this single field is the fastest health check for any BGP peering relationship, physical or cloud hybrid connection.

**Common errors:** A session stuck in `Active` state (BGP's terminology for "actively trying and failing to connect," confusingly not meaning "successfully active") almost always indicates a basic TCP reachability problem (port 179 blocked by a firewall/security group, an ACL, or an incorrect peer IP) rather than a BGP-specific configuration issue — checking basic Layer 3/4 connectivity to the peer on port 179 is the correct first step, not re-examining BGP-specific parameters.

### 5.2 Reading and Interpreting an AS-Path

**Purpose:** Read a real BGP AS-path to understand exactly which autonomous systems a route has traversed, and use it to reason about path preference.

**Syntax:**

```text
show ip bgp <prefix>
```

**Example usage and expected output:**

```text
Router# show ip bgp 10.20.0.0/16
BGP routing table entry for 10.20.0.0/16
Paths: (2 available, best #2)
  64515 64516 64520
    203.0.113.5 from 203.0.113.5 (203.0.113.5)
      Origin IGP, localpref 100, valid, external
  64513 64520
    203.0.113.1 from 203.0.113.1 (203.0.113.1)
      Origin IGP, localpref 150, valid, external, best
```

**Production usage example:** In this output, path #2 (AS-path `64513 64520`, only 2 hops) is marked `best` — and while it does happen to have the shorter AS-path here too, the actual deciding factor shown is `localpref 150` versus `localpref 100`: this router's own configured Local Preference policy prefers routes via AS 64513, and Local Preference is evaluated before AS-path length in BGP's best-path algorithm, so even if path #1's AS-path had been shorter, path #2 would still win on Local Preference alone.

**Common errors:** Assuming the visibly shorter AS-path always explains why a route was selected, without checking Local Preference, Weight, or MED first — misreading the actual deciding factor is one of the most common analytical mistakes when reviewing real BGP output, since multiple factors are often simultaneously present and only one is table-stakes.

## 6. Production Usage Notes

- **Cloud hybrid connectivity (Direct Connect, ExpressRoute, Cloud Interconnect) is essentially a managed BGP peering session** — the organization's on-premises router runs eBGP with the cloud provider's edge, exchanging routes for on-prem CIDRs and VPC/VNet CIDRs dynamically; understanding standard BGP session troubleshooting (peering state, AS-path, route acceptance/filtering) applies directly.
- **Most enterprise BGP usage never needs a public ASN** — private ASN ranges (64512-65534 for 16-bit ASNs; a larger reserved range exists for 32-bit ASNs) are standard for hybrid cloud connectivity and any BGP relationship that doesn't require globally unique registration with a Regional Internet Registry.
- **Route filtering (prefix-lists, AS-path filters, route-maps) is not optional hardening — it's core BGP hygiene.** Accepting every route a peer advertises with no filtering, or advertising every internal route with no summarization/control, is a common and serious operational risk regardless of whether the peering relationship is with the public internet or a private cloud hybrid connection.

## 7. Security Considerations

- **BGP hijacking** — an AS falsely announcing routes for address space it doesn't actually own or is not authorized to advertise — is a real, historically damaging internet-scale attack pattern; because BGP's original design has no built-in verification that an AS is authorized to originate a given prefix, other networks may accept and propagate a hijacked route, redirecting or black-holing traffic for the legitimate owner.
- **RPKI (Resource Public Key Infrastructure)** provides cryptographic **Route Origin Authorizations (ROAs)** that let a network verify whether an AS is actually authorized to originate a given prefix, and is the primary modern mitigation for BGP hijacking — increasingly deployed by major ISPs and cloud providers, though adoption is not yet universal across the entire internet.
- **Route leaks** (an AS unintentionally advertising routes it learned from one peer/provider to another, violating the intended commercial routing policy — for example, leaking a full internet routing table it received from a transit provider out to a peer that shouldn't see it) are distinct from hijacking (leaks involve real, legitimately learned routes propagated to the wrong place, not falsely originated ones) but can cause equally severe outages; **prefix-lists and AS-path filters** on every eBGP session are the standard mitigation for both hijacks and leaks at the local level.
- BGP sessions themselves should be protected with **TCP MD5 authentication** (or TCP-AO where supported) at minimum, since an unauthenticated BGP session is vulnerable to session hijacking or injection by anyone able to reach the peering endpoint at the network layer.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Likely Cause                                                                                          | Resolution Path                                                                                                             |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| BGP session stuck in `Active` or `Connect` state, never reaching `Established` | Basic TCP/port 179 reachability failure — firewall, security group, or ACL blocking the session, or incorrect peer IP | Verify Layer 3/4 reachability to the peer on TCP port 179 before checking any BGP-specific configuration                     |
| A route is received from a peer but isn't installed/preferred as expected | Another candidate path has a higher Weight, Local Preference, or otherwise wins BGP's best-path selection ahead of AS-path length | `show ip bgp <prefix>` to review all candidate paths and their attributes, not just the AS-path length, to find the actual deciding factor |
| Traffic to a specific external prefix suddenly takes an unexpected, longer path | A route leak or hijack from another AS, or an intentional policy change (Local Preference, MED) by a remote AS, altered advertised paths | Compare the current AS-path/attributes against known-good baseline; check for RPKI validation failures if hijacking is suspected |

## 9. Best Practices

- Apply explicit prefix-list and AS-path filtering on every eBGP session in both directions (inbound and outbound) — never rely on a peer's or provider's good behavior alone to prevent accidental route leaks or acceptance of bogus routes.
- Enable RPKI-based Route Origin Validation wherever the platform and upstream providers support it, as a meaningful mitigation against accepting hijacked routes.
- Document the intended Local Preference and MED policy for every BGP peering relationship explicitly — since these, not AS-path length, are usually the actual deciding factors in path selection, undocumented policy is the most common source of "why is traffic taking this path" confusion during incidents.

## 10. Common Anti-Patterns / Mistakes

- **Assuming BGP always selects the shortest AS-path**, when in practice Weight and Local Preference (pure local policy, unrelated to actual path length) are evaluated first on most implementations and frequently override AS-path length entirely.
- **Running eBGP sessions with no inbound/outbound route filtering**, accepting a peer's full routing table or advertising internal-only routes externally with no boundary control — a significant, avoidable operational and security risk.
- **Treating a BGP session stuck in `Active` state as a BGP configuration problem** and repeatedly re-checking AS numbers/route-maps, when the actual cause is nearly always a basic network-layer reachability failure to the peer on TCP port 179.

## 11. Interview Questions

**🎯 Beginner:** _"What does 'path-vector' mean in the context of BGP, and how is it different from a distance-vector or link-state protocol?"_
**Model answer:** Path-vector means every BGP route advertisement carries the full ordered list of Autonomous Systems (the AS-path) it has traversed, not just a distance value (like RIP's hop count, a distance-vector protocol) and not a full topology map of individual links (like OSPF's link-state model). The AS-path serves both as loop prevention — a router rejects any route whose AS-path already contains its own AS number — and as one input into path preference, though not the only or even primary one.
_What the interviewer is probing for:_ Whether the candidate can place path-vector as a genuinely distinct third category, not just "BGP is like RIP but for bigger networks."

**🎯 Intermediate:** _"What's the difference between eBGP and iBGP, and why does an organization need both?"_
**Model answer:** eBGP (external BGP) is used between routers in different autonomous systems — it's how an organization exchanges routes with its ISP, a cloud provider, or a partner network at the actual trust/administrative boundary. iBGP (internal BGP) is used between routers within the same autonomous system, and its purpose is to propagate externally learned routes across that AS's own internal network — without iBGP, only the specific edge router that directly received an external route via eBGP would know about it, and no other router inside the AS would have visibility into it. An organization with more than one edge router connecting to external networks needs iBGP internally so that externally learned routing information is consistently available throughout its own network.
_What the interviewer is probing for:_ Whether the candidate understands iBGP's actual purpose (internal propagation of externally learned routes) rather than just knowing the two terms exist.

**🎯 Senior:** _"A network engineer says 'BGP always picks the shortest path, that's the whole point of the AS-path.' How would you correct this, and what does BGP actually optimize for?"_
**Model answer:** AS-path length is real and does factor into BGP's best-path selection, but it's just one criterion in a longer, ordered list — and it's evaluated *after* higher-priority local factors like Weight (locally significant only) and Local Preference (an AS's own explicit policy statement about which of several exit paths it prefers). This means an AS can, and routinely does, deliberately prefer a longer AS-path over a shorter one for business reasons — cost of a transit relationship, a peering agreement, traffic engineering — and that preference will win over a shorter competing path every time, because it's checked earlier in the algorithm. BGP is fundamentally policy-first: it's designed to let each autonomous system enforce its own business and traffic-engineering decisions, with pure path-length optimization as a comparatively low-priority tiebreaker rather than the primary goal — which is the opposite emphasis from an IGP like OSPF, where pure shortest/lowest-cost path actually is the primary goal because there's a shared trust domain with no competing business interests to arbitrate.
_What the interviewer is probing for:_ Whether the candidate has internalized BGP's policy-first design deeply enough to correct a common, plausible-sounding misconception with a concrete mechanistic explanation (the actual order of the best-path algorithm), not just an assertion that the statement is wrong.

**🎯 Architect:** _"You're designing multi-homed internet connectivity for a company using two ISPs, with a requirement that outbound traffic prefer ISP A under normal conditions but automatically fail over to ISP B if ISP A's link degrades or fails. How do you achieve this with BGP, and what are the failure modes to watch for?"_
**Model answer:** I'd establish eBGP sessions with both ISPs and use Local Preference to express the outbound preference for ISP A — setting a higher Local Preference on routes learned via ISP A than on the equivalent routes via ISP B ensures the company's own internal routers prefer exiting via ISP A under normal conditions, since Local Preference is evaluated early in the best-path algorithm and directly encodes exactly this kind of policy intent. For automatic failover, BGP's own session teardown handles the case of a hard link/session failure reasonably well — if the eBGP session to ISP A goes down entirely, routes learned via it are withdrawn and traffic naturally shifts to the ISP B path — but I'd specifically watch for the "degraded but not down" failure mode: a link with high packet loss or a routing issue partway through ISP A's network that doesn't cause the local eBGP session itself to fail. Plain BGP has no native way to detect that kind of degradation, so I'd pair the design with BFD (Bidirectional Forwarding Detection) for faster session-failure detection than BGP's own timers provide, and separately with active monitoring/synthetic testing of actual end-to-end reachability through each ISP so a "BGP session is up but the path behind it is bad" scenario gets caught and can trigger a manual or automated Local Preference adjustment rather than silently continuing to send traffic down a degraded path that BGP itself has no visibility into.
_What the interviewer is probing for:_ Whether the candidate can design a real multi-homing policy using the correct BGP attribute (Local Preference, not just AS-path manipulation) and, critically, identifies BGP's blind spot around "up but degraded" links rather than assuming BGP alone provides complete failure detection.

## 12. Common Misconceptions

1. **"BGP always selects the shortest AS-path — that's its whole purpose."** AS-path length is one of several best-path criteria, evaluated after higher-priority local policy factors (Weight, Local Preference); BGP is policy-first, not shortest-path-first.
2. **"A BGP session in 'Active' state means it's actively working."** In BGP terminology, `Active` specifically means the router is actively attempting (and currently failing) to establish the TCP session — it is not a healthy state; `Established` is the state indicating a successful, working session.
3. **"BGP hijacking and route leaks are the same thing."** A hijack is a false origination of a prefix an AS doesn't own; a leak is the unintended propagation of a legitimately learned route to a peer or provider it shouldn't have been advertised to — different mechanisms, though both can cause similarly severe outages and both are mitigated substantially by route filtering.
4. **"Cloud hybrid connectivity (Direct Connect, ExpressRoute) uses some proprietary cloud-specific routing protocol."** It uses standard BGP (eBGP specifically) — the same protocol running the public internet — just presented through cloud-provider-specific setup tooling and typically using private ASNs.

## 13. 🔑 Key Takeaways

- BGP is a path-vector EGP: every route carries an explicit AS-path, which serves simultaneously as loop prevention and as one (not the primary) input to path preference.
- BGP's best-path selection is policy-driven and evaluates several factors (Weight, Local Preference, AS-path length, origin, MED, and more) in a defined order — AS-path length is a mid-priority tiebreaker, not the primary decision factor.
- eBGP connects different autonomous systems at their trust boundary; iBGP propagates externally learned routes across a single AS's own internal network so all its edge routers have consistent visibility.
- BGP hijacking (false origination) and route leaks (misdirected legitimate advertisements) are real, historically damaging internet failure modes, mitigated by route filtering (prefix-lists, AS-path filters) and increasingly by RPKI-based origin validation.
- Cloud hybrid connectivity (Direct Connect, ExpressRoute, Cloud Interconnect) is built directly on standard BGP, typically using private ASNs — the same protocol and concepts covered here apply directly.

## 14. Related Concepts & What's Next

[§29](Section-29-Part4-Dynamic-Routing-Overview-IGP-vs-EGP.md) established BGP's role as the sole practical EGP within the broader IGP/EGP landscape. [§30](Section-30-Part4-Distance-Vector-Protocols-RIP-Concepts.md) and [§31](Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md) (RIP and OSPF) provide the distance-vector and link-state contrast that clarifies why path-vector is a genuinely distinct third design. [§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)'s longest-prefix-match remains the final forwarding rule once BGP's own best-path algorithm has selected a preferred route among competing candidates. [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) covers route redistribution between BGP and IGPs, and administrative distance for ranking BGP-learned routes against statically or IGP-learned ones. [§106](../Part12/Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md) revisits BGP specifically in the context of cloud hybrid connectivity in additional depth.

**Next Section:** [§33](Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) — `Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md`
