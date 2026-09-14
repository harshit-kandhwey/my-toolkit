# Section 131 (Part 16): Enterprise Network Architecture Patterns (Three-Tier, Spine-Leaf)

## 1. Definition

**Plain language:** When you wire up a home lab or a small office, you can get away with a flat pile of switches and a router. A data center serving thousands of servers cannot — it needs a deliberate, layered blueprint that determines how traffic gets from any server to any other server, to the internet, and to other facilities, without the network itself becoming the bottleneck or the single point of failure. Two such blueprints dominate real-world enterprise and data-center design: the older **three-tier hierarchical model** and the modern **spine-leaf (Clos) fabric**.

**Precise definition:** The **three-tier architecture** organizes switching into a **core layer** (high-speed backbone, minimal packet manipulation), a **distribution/aggregation layer** (policy enforcement, inter-VLAN routing, redundancy boundary), and an **access layer** (where end hosts physically connect, per [§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md) and [§42](../Part5/Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)). The **spine-leaf architecture** — a two-tier Clos topology — instead connects every **leaf switch** (host-facing, analogous to access) to **every spine switch**, with no direct leaf-to-leaf or spine-to-spine links, guaranteeing a constant, predictable number of hops (leaf → spine → leaf) between any two servers regardless of fabric size. Spine-leaf is the standard modern data-center fabric because it scales horizontally by adding spines/leaves rather than by adding hierarchy, and it is built to run active-active across all links using ECMP rather than depending on Spanning Tree Protocol's active-passive blocking behavior ([§40](../Part5/Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)).

> 💡 **Tip:** The single fact worth memorizing: three-tier trades predictable latency for hierarchical simplicity, while spine-leaf trades a flatter, more cabling-intensive topology for constant hop-count and full bandwidth utilization on every link. Almost every large modern cloud/data-center design question in this space reduces to that trade-off.

## 2. Why This Matters

- **Every cloud provider's own physical data centers, and most large enterprises' server rooms, are built on some variant of spine-leaf** — understanding it is what lets an infrastructure engineer reason intelligently about the physical substrate underneath their VPCs ([§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)) and Kubernetes clusters ([§111](../Part13/Section-111-Part13-The-Kubernetes-Networking-Model-Pod-to-Pod-Service-and-Ingress-Concepts.md)), even though it is normally abstracted away.
- **Three-tier is still the dominant design in campus and branch-office networks** — an engineer who only knows spine-leaf will misread the topology diagrams of nearly every traditional enterprise office network they encounter.
- **The choice of topology directly determines how STP ([§40](../Part5/Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)) and link aggregation ([§41](../Part5/Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md)) do or don't get used** — spine-leaf fabrics are specifically designed to avoid the bandwidth waste that STP's loop-blocking imposes on three-tier designs.
- **Interviewers use this topic to test whether a candidate understands scaling design, not just device configuration** — "why would you choose spine-leaf over three-tier for a new data center" is a standard senior-level architecture question.
- **East-west traffic patterns in modern applications (microservices, distributed databases) are exactly what spine-leaf was designed to optimize for**, in contrast to the north-south-dominated traffic patterns three-tier was originally optimized for.

## 3. Prerequisites and Dependencies

This section assumes the switching fundamentals from [§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md) (hubs vs. switches vs. bridges), [§37](../Part5/Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) (broadcast vs. collision domains), and [§42](../Part5/Section-42-Part5-Layer-2-vs-Layer-3-Switching.md) (Layer 2 vs. Layer 3 switching), and directly builds on the loop-prevention behavior of Spanning Tree Protocol from [§40](../Part5/Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md) and the link-bundling concepts in [§41](../Part5/Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md) (LACP/EtherChannel), since both topologies' bandwidth-utilization characteristics are explained entirely in terms of how each interacts with STP and ECMP. It also depends on the routing fundamentals in [§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) (routing tables and longest-prefix match) and the dynamic routing concepts in [§31](../Part4/Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md) (OSPF) and [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) (BGP), since spine-leaf fabrics commonly run a link-state or BGP-based routing protocol between leaf and spine rather than relying on Layer 2 switching alone. It connects forward to [§132](Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md), since high-availability techniques are what keep either topology resilient to individual device failure, and to [§138](Section-138-Part16-Scaling-Networking-for-Growth-From-Single-VPC-to-Multi-Region-Enterprise.md), since scaling a network for growth is fundamentally a decision about which of these topologies (or which evolution of one) to adopt.

## 4. Architecture / Conceptual Diagram

```text
   THREE-TIER HIERARCHICAL MODEL:

                    ┌─────────────┐   ┌─────────────┐
                    │   Core A    │◄─►│   Core B    │       Core layer:
                    └──────┬──────┘   └──────┬──────┘       high-speed backbone
                           │                 │
              ┌────────────┼─────────────────┼────────────┐
              │            │                 │            │
        ┌─────┴─────┐ ┌────┴──────┐   ┌──────┴────┐ ┌─────┴─────┐
        │  Dist 1   │ │  Dist 2   │   │  Dist 3   │ │  Dist 4   │  Distribution:
        └──┬─────┬──┘ └───┬────┬──┘   └──┬─────┬──┘ └──┬─────┬──┘  policy, routing
           │     │        │    │         │     │        │     │
        ┌──┴─┐ ┌─┴──┐  ┌──┴─┐ ┌┴───┐  ┌──┴─┐ ┌─┴──┐  ┌──┴─┐ ┌─┴──┐
        │Acc │ │Acc │  │Acc │ │Acc │  │Acc │ │Acc │  │Acc │ │Acc │   Access: hosts
        └────┘ └────┘  └────┘ └────┘  └────┘ └────┘  └────┘ └────┘   connect here


   SPINE-LEAF (CLOS) FABRIC — every leaf connects to every spine:

        ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
        │ Spine 1 │   │ Spine 2 │   │ Spine 3 │   │ Spine 4 │
        └──┬─┬─┬─┬┘   └──┬─┬─┬─┬┘   └──┬─┬─┬─┬┘   └──┬─┬─┬─┬┘
           │ │ │ └────────┼─┼─┼────────┼─┼─┼────────┘ │ │ │
           │ │ └──────────┼─┼─┼────────┼─┼─┼──────────┘ │ │
           │ └────────────┼─┼─┼────────┼─┼─┼────────────┘ │
      ┌────┴┐         ┌───┴┐│         ┌┴───┐          ┌───┴┐
      │Leaf1│         │Leaf2│         │Leaf3│         │Leaf4│    Leaves: hosts/
      └──┬──┘         └──┬──┘         └──┬──┘         └──┬──┘    ToR switches
         │                │               │               │
      [servers]        [servers]       [servers]       [servers]

   Any server ► its leaf ► ANY spine ► destination leaf ► destination server
   = constant 2-hop distance, regardless of fabric size (add more leaves/spines to scale).
```

- In three-tier, traffic between two access-layer hosts on different distribution blocks must climb to the core and back down — a variable-length path whose latency depends on where in the hierarchy the two endpoints sit.
- In spine-leaf, every leaf-to-leaf path is exactly two hops via some spine, and Equal-Cost Multi-Path (ECMP) routing spreads flows across every spine simultaneously — unlike STP's single active path per VLAN ([§40](../Part5/Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)), no link sits idle as a pure backup.
- Spine-leaf's uniform hop count is what makes it the standard fabric for the low, predictable latency that distributed databases and microservice meshes ([§113](../Part13/Section-113-Part13-Service-Mesh-Networking-Concepts-Sidecar-Proxies-mTLS.md)) depend on internally within a data center.

## 5. Hands-On

### 5.1 Recognizing a Three-Tier Topology From Its Routing/Switching Boundary

**Purpose:** Show how to identify, from configuration alone, where the Layer 2/Layer 3 boundary ([§42](../Part5/Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)) sits in a three-tier design — the single most important fact for troubleshooting it.

**Syntax:**

```text
show vlan brief                 # access/distribution layer, Layer 2 domain
show ip interface brief         # distribution/core layer, Layer 3 SVIs and uplinks
show spanning-tree summary      # confirms STP is active at access/distribution
```

**Example usage and expected output:**

```text
Switch(distribution)# show ip interface brief
Interface              IP-Address      Status   Protocol
Vlan10                 10.10.0.1       up       up
Vlan20                 10.20.0.1       up       up
TenGigE0/0/1           10.255.0.2      up       up   (uplink to core)
```

- The presence of routed SVIs (`Vlan10`, `Vlan20`) terminating at the distribution switch, with a routed uplink to the core, is the concrete signature of the classic three-tier design: Layer 2 stops at distribution, Layer 3 begins there and continues upward.

**Production usage example:** Campus and branch-office network audits routinely start by identifying this exact boundary, since it determines which failures (a bad access port vs. a bad distribution routing adjacency) require Layer 2 tools ([§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md), [§40](../Part5/Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)) versus Layer 3 tools ([§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md), [§116](../Part14/Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)).

**Common errors:** Assuming every switch in the hierarchy is doing the same job — access switches typically do not route at all, and treating an access switch's `show ip route` output as meaningful is a common troubleshooting misstep for engineers new to hierarchical designs.

### 5.2 Verifying ECMP Behavior on a Spine-Leaf Fabric

**Purpose:** Demonstrate the operational check that confirms a spine-leaf fabric is actually using all spine paths rather than accidentally collapsing to one, which is the entire performance rationale for choosing the topology.

**Syntax:**

```bash
# On a leaf switch running BGP or OSPF toward the spines:
show ip route <destination-leaf-loopback>
show ip cef exact-route <src-ip> <dst-ip>       # per-flow ECMP hash verification
```

**Example usage and expected output:**

```text
Leaf1# show ip route 10.255.4.4
Routing entry for 10.255.4.4/32
  Known via "bgp", distance 20
  * 10.255.1.1, via Spine1   (active, ECMP)
  * 10.255.1.2, via Spine2   (active, ECMP)
  * 10.255.1.3, via Spine3   (active, ECMP)
  * 10.255.1.4, via Spine4   (active, ECMP)
```

- Four equal-cost next hops listed as simultaneously active — not one active and three standby — is exactly the signature that distinguishes a healthy spine-leaf fabric from a topology that has quietly degraded into using only a subset of its spines.

**Production usage example:** Data-center network operators routinely spot-check ECMP path counts after adding new spines, since a leaf that isn't forming the expected number of equal-cost adjacencies is silently running at reduced aggregate bandwidth without any obvious link-down alarm.

**Common errors:** Assuming that because all spine links show "up" at Layer 1, traffic is actually being load-balanced across them — a routing protocol misconfiguration (e.g., mismatched OSPF cost or a missing BGP neighbor per [§31](../Part4/Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md)/[§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) can leave a link physically up but never selected, which only `show ip route` or flow-hash verification reveals.

## 6. Production Usage Notes

- **New data-center builds default to spine-leaf** — it is now the de facto standard recommended by every major switch vendor and is what underlies the physical fabric of AWS, Azure, and GCP's own data centers, even though that fabric is invisible from inside a VPC/VNet ([§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)).
- **Existing campus and branch networks overwhelmingly remain three-tier**, both because their traffic patterns (client-to-server, north-south dominant) fit the model reasonably well and because a full re-cabling to spine-leaf is rarely justified outside a data center.
- **Spine-leaf fabrics are commonly built as a two-tier Clos and only grow a third "super-spine" tier when a single data hall's fabric needs to interconnect with other halls** — this three-tier Clos variant should not be confused with the classic core/distribution/access three-tier model; the terminology overlap is a frequent source of confusion in interviews and documentation alike.

## 7. Security Considerations

- Both topologies benefit from the segmentation principles in [§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) and the ACL-based micro-segmentation in [§90](../Part10/Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md), but the *enforcement point* differs: three-tier concentrates policy at the distribution layer, while spine-leaf typically pushes segmentation to the leaf (top-of-rack) switch, closest to the host, in keeping with zero-trust's preference for enforcing controls as close to the workload as possible.
- A compromised core or spine device is a catastrophic single point of failure for confidentiality and availability across the entire fabric — both designs depend on the redundancy and failover disciplines covered in [§132](Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md) to ensure no single core/spine device's compromise or failure takes down all paths at once.
- Fabric-wide routing protocols (OSPF/BGP per [§31](../Part4/Section-31-Part4-Link-State-Protocols-OSPF-Concepts.md)/[§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) running between leaf and spine should be authenticated, since an attacker who can inject routes into the fabric's own routing protocol can redirect or black-hole east-west traffic between workloads that believe they are on a trusted internal network.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| Intermittent high latency between two access-layer hosts in a three-tier network | Traffic traversing up to the core and back down across distribution blocks | Trace the actual path with `traceroute`/`mtr` ([§116](../Part14/Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)) and consider whether the two hosts should share a distribution block |
| One spine in a spine-leaf fabric carries visibly less traffic than the others | ECMP hashing skew, a flapping/degraded link, or a routing adjacency that only partially formed | Verify equal-cost paths with `show ip route`/`show ip cef exact-route` and check the routing protocol's neighbor state to that spine |
| Adding a new leaf switch doesn't improve available bandwidth as expected | New leaf not cabled to every spine, breaking the full-mesh assumption Clos math depends on | Audit physical cabling against the Clos wiring plan; a partially connected leaf behaves as an undersized leaf, not a full one |
| A single access switch failure takes down an entire distribution block in a three-tier network | No redundant access-to-distribution uplink, or STP blocking the only redundant path | Add a redundant uplink with a link-aggregation bundle ([§41](../Part5/Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md)) or verify STP is correctly load-sharing across available paths |

## 9. Best Practices

- Choose spine-leaf by default for any new data-center or private-cloud fabric build, reserving three-tier for campus/branch networks where its simpler hierarchy and lower cabling density remain genuinely appropriate.
- Size a spine-leaf fabric's spine count for both current east-west bandwidth needs and future horizontal growth, since adding spines later is possible but adding them non-uniformly across all existing leaves is operationally disruptive.
- Push segmentation and security policy ([§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md), [§90](../Part10/Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md)) as close to the host as the topology allows — the leaf/access layer — rather than relying solely on a core/distribution chokepoint that concentrates both a performance bottleneck and a single point of policy failure.

## 10. Common Anti-Patterns / Mistakes

- **Building a new data center on three-tier out of familiarity, without evaluating whether spine-leaf's scaling and bandwidth-utilization advantages apply.** Legacy vendor relationships and staff familiarity are real constraints, but they should be an explicit trade-off decision, not a default.
- **Treating "spine-leaf" and "Clos fabric with a super-spine tier" as contradictory rather than as the same family of design at different scales**, leading to confusion when a growing fabric legitimately needs a third tier.
- **Relying on Spanning Tree Protocol ([§40](../Part5/Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)) inside a spine-leaf fabric instead of a proper Layer 3 (OSPF/BGP) or EVPN-based control plane**, which reintroduces the single-active-path bandwidth waste that spine-leaf was specifically adopted to eliminate.

## 11. Interview Questions

**🎯 Beginner:** _"What are the three layers in a traditional three-tier network architecture, and what is each one responsible for?"_
**Model answer:** Core, distribution, and access. The access layer is where end hosts physically connect (switch ports per [§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md)). The distribution/aggregation layer enforces policy, performs inter-VLAN routing, and provides the redundancy boundary between multiple access switches. The core layer is a high-speed backbone that moves traffic between distribution blocks and out to other parts of the network, doing as little packet manipulation as possible to keep latency low.
_What the interviewer is probing for:_ Basic familiarity with hierarchical network design vocabulary before moving to more advanced topology questions.

**🎯 Intermediate:** _"Why is spine-leaf considered better suited to modern data-center traffic patterns than three-tier?"_
**Model answer:** Modern data-center traffic is dominated by east-west flows — server-to-server, microservice-to-microservice, database replication — rather than the north-south client-to-server pattern three-tier was designed around. Spine-leaf gives every leaf-to-leaf path a constant two-hop distance through any spine, and uses ECMP to actively load-balance across every spine simultaneously, rather than relying on Spanning Tree Protocol's single-active-path behavior, which leaves redundant links idle. This gives spine-leaf both lower and more predictable latency and full utilization of available bandwidth for exactly the traffic pattern that dominates inside a modern data center.
_What the interviewer is probing for:_ Understanding that topology choice should follow actual traffic patterns, not just be a default engineering habit.

**🎯 Senior:** _"You're troubleshooting a spine-leaf fabric where application teams report inconsistent latency between certain pairs of hosts, but not others. Walk through your diagnostic approach."_
**Model answer:** I'd first confirm this isn't actually a Layer 3/application-layer issue outside the fabric by checking whether the affected host pairs share the same leaf switches consistently. If the pattern correlates with specific leaf-spine paths, I'd check ECMP hash distribution with `show ip cef exact-route` to see whether certain flows are consistently landing on a specific, possibly degraded, spine. I'd also check for asymmetric routing ([§121](../Part14/Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md)) if leaf uplinks aren't uniformly provisioned, and verify that all spines show as active, equal-cost next hops from the affected leaves rather than one being silently excluded due to a routing adjacency problem. Physical-layer checks (interface errors, CRC counters) on the specific spine and leaf uplinks involved would follow if the routing-level picture looks healthy but latency still correlates with a specific physical path.
_What the interviewer is probing for:_ A systematic, layer-aware diagnostic process ([§115](../Part14/Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md)) applied specifically to the ECMP and ECMP-hashing characteristics unique to spine-leaf fabrics, rather than generic network troubleshooting.

**🎯 Architect:** _"Design the data-center fabric strategy for a company building three new regional data centers that need to support rapidly scaling microservice workloads, with an expectation of doubling server count within two years."_
**Model answer:** I'd standardize on a spine-leaf Clos fabric per data hall, sized with enough spine ports to accommodate the projected leaf count at full two-year growth without a disruptive spine-tier redesign, since retrofitting spine count non-uniformly across existing leaves is operationally painful. I'd run BGP ([§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) or a link-state protocol between leaf and spine rather than relying on Layer 2/STP ([§40](../Part5/Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)), both for the ECMP benefits and because BGP-based fabrics scale administrative complexity better as the leaf count grows. If any single data hall is projected to outgrow what one spine tier can economically support, I'd plan for a super-spine tier to interconnect multiple spine-leaf pods within that hall, keeping the same Clos principles at a larger scale. Segmentation and security policy ([§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)) would be enforced at the leaf/top-of-rack layer, closest to the workloads, and each data hall's fabric would connect outward through a well-defined hybrid/interconnect boundary ([§106](../Part12/Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md)) rather than blurring fabric-internal and cross-site routing in the same control plane.
_What the interviewer is probing for:_ The ability to make a topology decision that accounts for multi-year growth, protocol choice, and security posture together, rather than treating fabric design as a purely physical-layer decision.

## 12. Common Misconceptions

1. **"Spine-leaf is always strictly better than three-tier and should replace it everywhere."** Three-tier remains entirely appropriate for campus/branch networks with client-server-dominant traffic and lower east-west bandwidth needs.
2. **"A 'three-tier Clos fabric' with a super-spine layer is a different architecture from spine-leaf."** It is the same Clos design family scaled to a third tier, not a competing topology.
3. **"Adding more spines to a fabric always proportionally increases available bandwidth."** It only does so if every existing leaf is also re-cabled to the new spines; a partial rollout leaves the Clos full-mesh assumption broken for the affected leaves.
4. **"STP is irrelevant once you adopt spine-leaf."** STP-family concepts remain relevant for any residual Layer 2 segments in a fabric; a well-designed spine-leaf fabric is Layer 3 (or EVPN-based) specifically to avoid depending on STP for its core leaf-spine paths.

## 13. 🔑 Key Takeaways

- Three-tier (core/distribution/access) remains the standard for campus and branch networks; spine-leaf (Clos) is the standard for modern data-center fabrics built around east-west traffic.
- Spine-leaf's defining property is a constant two-hop distance between any two leaves, achieved by connecting every leaf to every spine and using ECMP rather than STP's single-active-path model.
- The Layer 2/Layer 3 boundary sits at distribution in three-tier designs; spine-leaf fabrics typically run Layer 3 (or EVPN) all the way to the leaf to unlock full ECMP utilization.
- Both topologies depend on the high-availability and redundancy techniques in [§132](Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md) to avoid any single core/spine device becoming a catastrophic point of failure.
- Segmentation and security policy enforcement should sit as close to the host as the topology allows — distribution in three-tier, leaf/top-of-rack in spine-leaf.

## 14. Related Concepts & What's Next

This section's topology choices set the physical and logical stage for [§132](Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md)'s discussion of redundancy and failover mechanisms, since HSRP/VRRP-style protocols and ECMP both exist to keep either topology resilient to individual device loss. It also connects forward to [§138](Section-138-Part16-Scaling-Networking-for-Growth-From-Single-VPC-to-Multi-Region-Enterprise.md), where the decision to evolve a network's topology entirely is framed as part of a broader multi-region scaling story, and back to [§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md) and [§111](../Part13/Section-111-Part13-The-Kubernetes-Networking-Model-Pod-to-Pod-Service-and-Ingress-Concepts.md), since the cloud VPC/VNet and Kubernetes networking models covered there both run, invisibly, atop a spine-leaf fabric at the physical layer.

**Next Section:** [§132](Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md) — `Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md`
