# Section 39 (Part 5): Inter-VLAN Routing

## 1. Definition

**Plain language:** VLANs deliberately stop devices in different VLANs from talking to each other at Layer 2 — that's the whole point of a VLAN. But real networks need VLAN-10 hosts to reach VLAN-20 hosts sometimes (a web server VLAN needs to reach a database VLAN, for instance). Inter-VLAN routing is how that crossing happens: something has to sit between the VLANs and forward traffic at Layer 3 (by IP address), because nothing at Layer 2 is willing to do it.

**Precise definition:** **Inter-VLAN routing** is the process of forwarding traffic **between** VLANs, which requires a Layer 3 device — because VLANs are separate broadcast domains ([§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)), no amount of Layer 2 switching alone can move traffic between them. Historically this was implemented as **"router-on-a-stick"**: a single physical router interface, configured with **802.1Q sub-interfaces** ([§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)) — one sub-interface per VLAN, each with its own IP address acting as that VLAN's default gateway — connected to a switch trunk port carrying all the relevant VLANs. Modern deployments more commonly use a **Layer 3 switch** ([§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)): a switch with **Switched Virtual Interfaces (SVIs)**, one per VLAN, performing the same gateway/routing function natively in switch hardware without needing an external router or a physical trunk link at all.

> 💡 **Tip:** Every inter-VLAN routing design answer to "how does traffic get from VLAN A to VLAN B" is really the same answer at different levels of integration: something with an IP address in VLAN A and an IP address in VLAN B (or one interface per VLAN) has to receive the frame, strip it down to the IP packet, make a routing decision, and re-encapsulate it into a new frame for the destination VLAN. Router-on-a-stick and Layer 3 switch SVIs are two different physical/logical packagings of that exact same operation.

## 2. Why This Matters

- **This is the mechanism that makes VLAN segmentation practical rather than merely isolating.** Segmenting a network into VLANs ([§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)) is only useful in production if legitimate cross-VLAN traffic (web tier to database tier, user VLAN to shared services VLAN) still has a defined, controllable path — inter-VLAN routing is that path.
- **The router/Layer 3 switch performing inter-VLAN routing is the natural, and often only, enforcement point for traffic policy between environments** — firewalls, ACLs, and security groups conceptually attach exactly here, which is why "put a firewall between VLANs" and "route between VLANs" are, in traditional network design, often the same physical device doing both jobs.
- **A missing or misconfigured default gateway on a VLAN is one of the most common "this host can't reach anything outside its own subnet" root causes** — understanding that a VLAN's gateway is a specific IP address on a specific router sub-interface or SVI makes this class of problem immediately diagnosable rather than mysterious.
- **This is the direct conceptual precursor to cloud VPC routing** — a cloud VPC's route table directing traffic between subnets is functionally the cloud-native, software-defined descendant of inter-VLAN routing, just abstracted away from any single physical device.
- **Router-on-a-stick vs. Layer 3 switch SVI is a real, still-relevant architectural choice** in on-prem and colo environments, with genuine trade-offs in throughput, single point of failure, and cost that come up in actual network design decisions.

## 3. Prerequisites and Dependencies

Builds directly on [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) (VLANs, tagging, trunking) — inter-VLAN routing assumes VLANs, trunk ports, and 802.1Q tagging are already understood, since router-on-a-stick is built entirely on top of a trunk link. [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) (broadcast domains) explains why this routing step is necessary at all — VLANs are separate broadcast domains by definition, and only a Layer 3 device bridges that gap. [§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) (Part 4, routing fundamentals) is directly relevant background on what "routing" and "default gateway" mean generally, applied here specifically at the VLAN boundary. [§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md) (Layer 2 vs. Layer 3 switching) is the natural next step, formalizing the SVI-based approach only introduced here and contrasting it fully against router-on-a-stick.

## 4. Architecture / Conceptual Diagram

```text
   ROUTER-ON-A-STICK                          LAYER 3 SWITCH WITH SVIs

   ┌────────────┐                             ┌─────────────────────────┐
   │   Router   │                             │      Layer 3 Switch     │
   │            │                             │                          │
   │ eth0.10 ───┼── 10.0.10.1 (VLAN 10 GW)    │  SVI VLAN10: 10.0.10.1  │
   │ eth0.20 ───┼── 10.0.20.1 (VLAN 20 GW)    │  SVI VLAN20: 10.0.20.1  │
   │            │                             │  (routing done in       │
   │  ONE       │                             │   hardware, no          │
   │  physical  │                             │   external trunk        │
   │  trunk     │                             │   needed)                │
   │  link      │                             │                          │
   └─────┬──────┘                             │  Port 1 (VLAN 10)-PC-A  │
         │ trunk (802.1Q, VLAN 10 + 20)       │  Port 2 (VLAN 20)-PC-B  │
   ┌─────┴──────┐                             └─────────────────────────┘
   │   Switch   │
   │ Port 1 (VLAN 10) -- PC-A (10.0.10.5, gw 10.0.10.1)
   │ Port 2 (VLAN 20) -- PC-B (10.0.20.5, gw 10.0.20.1)
   └────────────┘

   PC-A → PC-B path (router-on-a-stick):
   PC-A sends to its gateway (10.0.10.1) → frame tagged VLAN 10 crosses trunk to
   router's eth0.10 → router routes IP packet to eth0.20 → frame re-tagged VLAN 20,
   crosses trunk back to switch → delivered to PC-B.  Note: traffic crosses the
   SAME physical trunk link TWICE (once per direction of the Layer 3 hop).
```

- **Router-on-a-stick** uses one physical link (a trunk) and multiple logical sub-interfaces, one per VLAN, each acting as that VLAN's default gateway. All inter-VLAN traffic traverses the same physical trunk twice (once into the router, once back out) — a real, sometimes limiting, bandwidth consideration on higher-traffic networks.
- **Layer 3 switch SVIs** eliminate the external trunk round-trip entirely: the switch itself holds an IP interface (SVI) per VLAN and performs the routing lookup internally, in hardware, without traffic ever leaving the switch chassis for the routing step. This is why most modern data center designs use Layer 3 switching rather than router-on-a-stick wherever throughput matters.
- Either way, the **default gateway** configured on every end host is the IP address of that host's VLAN's routing interface (sub-interface or SVI) — this is the concrete, singular fact that makes cross-VLAN connectivity work or fail.

## 5. Hands-On

### 5.1 Configuring Router-on-a-Stick on Linux (Simulated Router)

**Purpose:** Build a working router-on-a-stick setup using a Linux host as the routing device, directly demonstrating the VLAN sub-interface + IP forwarding combination that makes inter-VLAN routing work.

**Syntax:**

```bash
ip link add link <trunk-iface> name <trunk-iface>.<vlan-id> type vlan id <vlan-id>
ip addr add <gateway-ip>/<prefix> dev <trunk-iface>.<vlan-id>
sysctl -w net.ipv4.ip_forward=1
```

**Example usage and expected output:**

```bash
$ sudo ip link add link eth0 name eth0.10 type vlan id 10
$ sudo ip link add link eth0 name eth0.20 type vlan id 20
$ sudo ip addr add 10.0.10.1/24 dev eth0.10
$ sudo ip addr add 10.0.20.1/24 dev eth0.20
$ sudo ip link set eth0.10 up && sudo ip link set eth0.20 up
$ sudo sysctl -w net.ipv4.ip_forward=1
net.ipv4.ip_forward = 1
$ ip route show
10.0.10.0/24 dev eth0.10 proto kernel scope link src 10.0.10.1
10.0.20.0/24 dev eth0.20 proto kernel scope link src 10.0.20.1
```

**Production usage example:** Small offices and lab environments frequently use exactly this pattern — a single Linux host (or a small firewall appliance running Linux underneath, like many open-source firewall distributions) with one trunked physical NIC serving as the inter-VLAN router for several VLANs, avoiding the cost of a dedicated Layer 3 switch for low-throughput environments.

**Common errors:** Forgetting `net.ipv4.ip_forward=1` — without it, the Linux host will correctly receive packets on both sub-interfaces but will never forward traffic between them, silently dropping cross-VLAN packets while each VLAN's local traffic continues working fine, which is a confusing partial-failure symptom.

### 5.2 Verifying a Host's Default Gateway and Route to Another VLAN

**Purpose:** Confirm, from an end host's perspective, exactly which gateway it will use to reach a different VLAN's subnet — the single most common inter-VLAN routing troubleshooting check.

**Syntax:**

```bash
ip route show
ip route get <destination-ip>
```

**Example usage and expected output:**

```bash
$ ip route show
default via 10.0.10.1 dev eth0
10.0.10.0/24 dev eth0 proto kernel scope link src 10.0.10.5

$ ip route get 10.0.20.7
10.0.20.7 via 10.0.10.1 dev eth0 src 10.0.10.5
```

**Production usage example:** When a host in VLAN 10 can't reach a host in VLAN 20, this is the very first check — confirming the source host actually has a correct default gateway (or a more specific route) pointing at the right router/SVI address, before investigating the router/switch side at all, since a wrong or missing gateway on the source host is a common misconfiguration (especially on statically configured hosts or ones with a stale DHCP lease).

**Common errors:** Assuming a correct default gateway on the source host guarantees connectivity — this only confirms the source host will send the packet toward the right place; the router/Layer 3 switch itself must also have correct routes and (if applicable) permit the traffic through any ACL/firewall policy for the connection to actually succeed end to end.

### 5.3 Testing and Tracing an Inter-VLAN Path

**Purpose:** Confirm the actual Layer 3 hop count and path a packet takes crossing from one VLAN to another, distinguishing a working single-hop inter-VLAN route from an unexpectedly longer or broken path.

**Syntax:**

```bash
traceroute <destination-ip>
ping -c 4 <destination-ip>
```

**Example usage and expected output:**

```bash
$ traceroute 10.0.20.7
traceroute to 10.0.20.7 (10.0.20.7), 30 hops max
 1  10.0.10.1 (10.0.10.1)  0.412 ms   0.398 ms   0.375 ms
 2  10.0.20.7 (10.0.20.7)  0.601 ms   0.589 ms   0.577 ms
```

**Production usage example:** Seeing exactly one intermediate hop (the gateway) between two VLANs confirms a correctly functioning direct inter-VLAN route; seeing zero hops (meaning the traceroute never left the source, usually an ARP/gateway resolution failure) or an unexpected number of additional hops (suggesting traffic is being routed through an unintended path, perhaps a misconfigured route or an unnecessary extra router) both point to specific, different root causes worth investigating separately.

**Common errors:** Interpreting `traceroute` timeouts (`* * *`) at a given hop as proof that hop is down — many routers and firewalls intentionally rate-limit or don't respond to the ICMP/UDP probes traceroute relies on, so a silent hop with working connectivity beyond it is common and not itself evidence of a fault.

## 6. Production Usage Notes

- **Router-on-a-stick's shared-trunk-bandwidth limitation is a real, measurable constraint**, not a theoretical one — because all inter-VLAN traffic crosses the same physical link twice, a router-on-a-stick design's effective inter-VLAN throughput ceiling is meaningfully lower than the link's nominal capacity, which is why it's typically reserved for lower-throughput or lab/small-office scenarios rather than data center core routing.
- **Layer 3 switch SVIs are the standard modern approach in data centers and campus networks** specifically because routing happens in switch hardware (ASIC) at line rate without an external trunk round-trip — [§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md) covers this device category and its trade-offs in depth.
- **The router/Layer 3 switch performing inter-VLAN routing becomes, by necessity, the place where cross-VLAN traffic policy is enforced** — this is why the same device (or a device sitting immediately behind it) commonly also runs ACLs or acts as a firewall for traffic transiting between VLANs, a pattern that later material in this roadmap on firewalls and security groups builds on directly.

## 7. Security Considerations

- **The inter-VLAN routing point is the natural place to enforce segmentation policy that VLANs alone cannot provide.** Because all cross-VLAN traffic must pass through this single Layer 3 chokepoint, it's the standard location for ACLs restricting which VLANs may reach which — e.g., explicitly denying a general user VLAN from initiating connections to a management VLAN, while still allowing the reverse.
- **A misconfigured or overly permissive inter-VLAN ACL defeats the isolation purpose of VLAN segmentation entirely** — VLANs alone stop Layer 2 reachability, but if the routing device between them permits all traffic by default, the segmentation provides no real security benefit beyond broadcast-domain scoping.
- **Router-on-a-stick's single physical trunk link is also a single point of Layer 3 policy enforcement and a single point of failure** — from a security and availability standpoint, this concentration is worth explicitly acknowledging in a design review rather than discovering during an incident.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                     | Resolution Path                                                                                                            |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Host can reach others in its own VLAN but nothing outside it                    | Missing, incorrect, or unreachable default gateway configuration on the host                        | `ip route show` on the host to confirm the default gateway; ping the gateway IP directly to isolate host-vs-router fault      |
| Two VLANs' hosts see each other's traffic partially fail (some flows work)       | Router-on-a-stick trunk link saturated (traffic crossing the shared link twice hits a bandwidth ceiling) | Check trunk link utilization; consider migrating to a Layer 3 switch with SVIs ([§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)) to remove the shared-link bottleneck  |
| Cross-VLAN traffic is unexpectedly blocked despite correct routing             | An ACL/firewall rule on the inter-VLAN routing device is denying the traffic                          | Review the routing device's ACL/policy configuration for the source/destination VLAN pair; confirm intended policy matches actual |

## 9. Best Practices

- Document each VLAN's default gateway address as part of the VLAN's own definition (alongside its ID and subnet), so "what's the gateway for VLAN 20" is never a guess during an incident.
- Prefer Layer 3 switching (SVIs) over router-on-a-stick for any environment where inter-VLAN throughput is a meaningful concern, reserving router-on-a-stick for genuinely low-traffic, small-scale, or lab scenarios.
- Treat the inter-VLAN routing device's ACL/policy configuration as a first-class, reviewed security control — changes here directly determine whether VLAN segmentation provides real isolation or is purely cosmetic.

## 10. Common Anti-Patterns / Mistakes

- **Assuming VLAN segmentation alone provides security isolation without checking what the inter-VLAN routing device actually permits.** If the router or Layer 3 switch allows all traffic between every VLAN by default, the VLANs are dividing broadcast domains but providing no meaningful access control.
- **Using router-on-a-stick for a high-throughput core routing role** where the shared-trunk bandwidth ceiling becomes a genuine, hard-to-diagnose performance bottleneck as traffic grows — this is a common "worked fine in the pilot, degraded at scale" mistake.
- **Leaving a host statically configured with a stale or incorrect default gateway** after a network redesign moves the gateway address (e.g., migrating from router-on-a-stick to a Layer 3 switch SVI with a different IP) — a classic, avoidable source of post-migration outages.

## 11. Interview Questions

**🎯 Beginner:** _"Why can't two hosts on different VLANs talk to each other directly, and what has to happen for them to communicate?"_
**Model answer:** VLANs are separate broadcast domains by design — a switch will never forward Layer 2 traffic between different VLANs on its own, since that's exactly what VLAN separation is meant to prevent. For two hosts on different VLANs to communicate, something has to route between them at Layer 3: a router or Layer 3 switch with an interface (or gateway address) in each VLAN receives the traffic, makes a routing decision based on the destination IP address, and forwards it into the destination VLAN.
_What the interviewer is probing for:_ Whether the candidate connects VLAN isolation (from [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)) to the specific need for a Layer 3 device to bridge it, rather than assuming switches can somehow route between VLANs on their own.

**🎯 Intermediate:** _"Compare router-on-a-stick and a Layer 3 switch with SVIs for inter-VLAN routing."_
**Model answer:** Both achieve the same logical outcome — one gateway interface per VLAN performing Layer 3 forwarding between them — but differently. Router-on-a-stick uses a single physical trunk link between an external router and a switch, with 802.1Q sub-interfaces on the router acting as each VLAN's gateway; all inter-VLAN traffic crosses that one physical link twice, which caps effective throughput at a fraction of the link's nominal bandwidth. A Layer 3 switch instead holds a Switched Virtual Interface per VLAN internally and routes between them in switch hardware, with no external trunk or physical round-trip needed, giving much higher effective throughput. Router-on-a-stick is simpler and cheaper for low-traffic or lab scenarios; Layer 3 switching is the standard choice wherever inter-VLAN throughput actually matters.
_What the interviewer is probing for:_ Whether the candidate understands the concrete architectural and performance difference, not just that "both do inter-VLAN routing."

**🎯 Senior:** _"A team reports that inter-VLAN traffic between their web and database VLANs is intermittently slow, but traffic within each VLAN is fine. What would you check first, and why?"_
**Model answer:** Given that intra-VLAN traffic is fine and only inter-VLAN traffic is affected, I'd focus on the Layer 3 device and path connecting the two VLANs rather than anything within either VLAN's own switching. First, I'd check whether inter-VLAN routing here is router-on-a-stick — if so, the shared trunk link carrying all inter-VLAN traffic twice is a strong suspect for saturation under load, and I'd check its utilization directly. If it's a Layer 3 switch with SVIs instead, I'd look at CPU/ASIC routing table load and any ACL processing overhead on that device, since those are the equivalent bottleneck points in that architecture. I'd also verify there isn't an asymmetric or unintended extra hop in the path (via traceroute) that only appears intermittently — a routing table inconsistency or a failover to a backup path can produce exactly this kind of intermittent-but-not-total symptom.
_What the interviewer is probing for:_ Whether the candidate localizes the fault to the Layer 3 device/path specifically (given the intra- vs. inter-VLAN symptom split) and reasons through the concrete bottleneck each architecture (router-on-a-stick vs. Layer 3 switch) would produce.

**🎯 Architect:** _"You're designing network connectivity for a new three-tier application (web, app, database) where each tier lives in its own VLAN. How do you architect inter-VLAN routing and policy, and what would make you choose router-on-a-stick versus a Layer 3 switch?"_
**Model answer:** I'd default to Layer 3 switching (SVIs) as the primary inter-VLAN routing mechanism, given that a production three-tier application's tier-to-tier traffic (web-to-app, app-to-database) is exactly the kind of throughput-sensitive, latency-sensitive path where router-on-a-stick's shared-trunk bottleneck would be a real risk as traffic scales. I would only consider router-on-a-stick for a genuinely low-traffic environment — a small internal tool, a lab/staging environment with light load — where the cost or complexity of a Layer 3 switch isn't justified. Beyond the routing mechanism itself, I'd treat the routing device as the enforcement point for tier-to-tier policy: explicit ACLs permitting only the specific traffic each tier legitimately needs from the next (web VLAN can reach app VLAN on its application port; app VLAN can reach database VLAN on its database port; nothing reaches database directly from the web VLAN), denying everything else by default. I'd also plan for redundancy at this Layer 3 boundary specifically, since it's now a single logical chokepoint for all cross-tier traffic — dual Layer 3 switches with a first-hop redundancy protocol, or an equivalent HA design, rather than a single device whose failure takes down all cross-tier communication at once.
_What the interviewer is probing for:_ Whether the candidate designs inter-VLAN routing as both a performance decision (Layer 3 switch vs. router-on-a-stick, scaled to actual traffic needs) and a security/policy decision (least-privilege ACLs between tiers) simultaneously, plus awareness of the new single-point-of-failure this Layer 3 boundary introduces.

## 12. Common Misconceptions

1. **"A trunk link by itself allows VLANs to communicate with each other."** A trunk only carries multiple VLANs' tagged traffic over one physical link — it does nothing to route between them; that still requires a Layer 3 device with an interface in each VLAN.
2. **"Router-on-a-stick and Layer 3 switching are functionally different features."** They achieve the identical logical outcome (one gateway per VLAN, routing between them) — the difference is entirely architectural (external router + trunk vs. internal SVI), not a difference in what's accomplished.
3. **"VLANs plus inter-VLAN routing automatically means the VLANs are securely isolated from each other."** Isolation depends entirely on what policy (ACLs/firewall rules) the routing device enforces — with no restrictive policy, inter-VLAN routing simply reconnects everything the VLANs separated, providing no security benefit.
4. **"A host's default gateway is a fixed, universal concept independent of VLAN design."** A host's default gateway is specifically the IP address of its own VLAN's routing interface — it changes if the VLAN's gateway is re-addressed or the routing architecture (router-on-a-stick to Layer 3 switch) changes, and stale gateway configuration after such a change is a common outage cause.

## 13. 🔑 Key Takeaways

- VLANs are separate broadcast domains by design, so crossing between them always requires a Layer 3 device — no purely Layer 2 mechanism can do it.
- Router-on-a-stick uses one external router with 802.1Q sub-interfaces over a single trunk link; a Layer 3 switch uses internal SVIs, routing in hardware without an external trunk round-trip.
- Router-on-a-stick's shared trunk bandwidth is a genuine throughput ceiling; Layer 3 switching is the standard modern choice wherever inter-VLAN traffic volume matters.
- The inter-VLAN routing device is the natural, often sole, enforcement point for cross-VLAN traffic policy — VLAN separation without restrictive policy here provides no real security isolation.
- A missing or incorrect default gateway on an end host is one of the most common and most quickly diagnosable inter-VLAN connectivity failures.

## 14. Related Concepts & What's Next

[§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md) is the direct continuation of this section, formalizing the Layer 3 switch/SVI approach introduced here and contrasting it comprehensively against pure Layer 2 switching. [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) is this section's prerequisite, covering the VLAN and trunking concepts router-on-a-stick depends on directly. [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) explains the underlying reason (broadcast domain separation) inter-VLAN routing is necessary at all. [§41](Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md) (Link Aggregation) is relevant to production router-on-a-stick and Layer 3 switch uplink designs, where the trunk or uplink itself is often bundled for redundancy and bandwidth. [§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md) (Part 12) revisits this exact routing concept in its cloud-native form — VPC route tables directing traffic between subnets.

**Next Section:** [§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md) — `Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md`
