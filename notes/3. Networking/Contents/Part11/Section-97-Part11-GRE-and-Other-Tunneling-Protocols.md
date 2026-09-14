# Section 97 (Part 11): GRE and Other Tunneling Protocols

## 1. Definition

**Plain language:** Not every tunnel needs encryption. Sometimes the only problem worth solving is "how do I carry this kind of traffic across a network that doesn't natively support it" — connecting two networks that use a routing protocol the path in between doesn't understand, or carrying non-IP traffic across an IP-only network. GRE is the simplest, oldest, and most widely supported answer to exactly that narrower problem.

**Precise definition:** **GRE (Generic Routing Encapsulation)**, standardized in RFC 2784, is a tunneling protocol that encapsulates an arbitrary payload — commonly another IP packet, but originally designed to carry any network-layer protocol — inside a new outer IP packet, using IP protocol number 47. Critically, **GRE by itself provides no encryption and no strong authentication** — it solves the encapsulation/reachability problem from [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md) without solving the confidentiality/integrity problem IPsec ([§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md)) or WireGuard ([§94](Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md)) solve. Because of this, GRE is very commonly deployed **combined with IPsec** — "GRE over IPsec" — where GRE handles multicast/broadcast traffic and dynamic routing protocol support that plain IPsec tunnel mode doesn't natively carry well, while IPsec wraps the resulting GRE tunnel for encryption. Beyond GRE, several other tunneling protocols solve related but distinct problems: **VXLAN (Virtual Extensible LAN)** encapsulates Layer 2 Ethernet frames inside UDP packets to build large-scale overlay networks (heavily used in data center and cloud networking, and by container/Kubernetes CNI plugins for pod-to-pod overlay networking); **GENEVE** is a newer, more extensible overlay encapsulation format designed to succeed VXLAN with a more flexible metadata model; and **L2TP (Layer 2 Tunneling Protocol)**, often paired with IPsec ("L2TP/IPsec") for encryption, tunnels Layer 2 frames and was historically common in consumer and some enterprise remote-access VPN products before largely being superseded by more modern alternatives.

> 💡 **Tip:** If a protocol description mentions "carries any protocol including non-IP traffic" or "supports multicast/broadcast across the tunnel" as a selling point, it's very likely GRE or a GRE-family protocol — IPsec tunnel mode alone, by contrast, is fundamentally built around encapsulating unicast IP traffic and doesn't natively handle multicast/broadcast or non-IP payloads the same way.

## 2. Why This Matters

- **GRE over IPsec is a common, real-world pattern for connecting networks that need dynamic routing protocols (like OSPF or EIGRP, which rely on multicast) across a tunnel** — plain IPsec tunnel mode alone doesn't naturally carry the multicast traffic these protocols depend on, while GRE does, making "GRE over IPsec" the practical answer rather than an obscure edge case.
- **VXLAN and GENEVE are foundational to how modern data center and cloud overlay networks (including container networking) actually work under the hood** — understanding tunneling as encapsulation directly demystifies otherwise-opaque cloud networking and Kubernetes CNI behavior.
- **GRE's complete lack of built-in encryption is a frequent source of security misunderstanding** — engineers unfamiliar with the distinction sometimes assume "it's a VPN-like tunnel" implies encryption, when a bare GRE tunnel provides none at all.
- **Legacy infrastructure and some vendor equipment still rely on GRE or L2TP/IPsec for interoperability reasons**, making familiarity with these older protocols practically relevant for hybrid or legacy-integration work, even as WireGuard and modern IPsec dominate new deployments.
- **This section rounds out the tunneling-protocol landscape** started in [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md), giving a complete picture of when encapsulation alone (GRE, VXLAN) is the right tool versus when encapsulation plus encryption (IPsec, WireGuard, SSL/TLS VPN) is actually needed.

## 3. Prerequisites and Dependencies

This section assumes the general encapsulation model introduced in [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md) and directly builds on the IPsec tunnel mode mechanics from [§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md), since GRE-over-IPsec is a composition of both. Basic familiarity with dynamic routing protocols and their reliance on multicast (briefly touched on in OSPF's coverage in Part 4) provides useful context for why GRE-over-IPsec is specifically needed in some site-to-site scenarios. Familiarity with VLANs and Layer 2/Layer 3 switching concepts ([§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md)–[§43](../Part5/Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md)) is helpful for understanding VXLAN's Layer 2-over-Layer 3 encapsulation model. This section is the last of Part 11's protocol-specific deep dives before [§98](Section-98-Part11-MPLS-Concepts-and-Where-It-Fits-in-Enterprise-WANs.md) and [§99](Section-99-Part11-SD-WAN-Conceptual-Overview.md) shift to broader enterprise WAN architecture concepts.

## 4. Architecture / Conceptual Diagram

```text
   Plain GRE tunnel (no encryption):

   Original packet ── GRE header (protocol 47) ── New outer IP header ──► Internet
        (visible to any observer who captures the tunnel traffic — GRE
         itself does nothing to hide or protect the payload)

   GRE over IPsec (the common production pattern):

   Original packet ── GRE header ── [ entire GRE packet encrypted by ESP ] ── Outer IP header ──► Internet
        (GRE provides multicast/non-IP/dynamic-routing-protocol support;
         IPsec wraps the whole thing for confidentiality and integrity)

   VXLAN overlay (data center / cloud / container networking):

   Original Ethernet frame ── VXLAN header (with VNI) ── UDP header ── Outer IP header ──► Underlay network
        (lets Layer 2 domains span across a Layer 3-routed underlay —
         the VNI (VXLAN Network Identifier) is like a VLAN ID, but with
         a vastly larger address space: ~16 million possible segments
         versus VLAN's 4094)
```

- **GRE's encapsulation happens one layer "above" where IPsec normally operates alone**, which is exactly why combining them works: GRE first wraps the original (possibly multicast or non-IP) packet into a GRE/IP packet, and IPsec then encrypts that entire GRE packet as its own payload, layering the two technologies' distinct strengths.
- **VXLAN's UDP-based encapsulation (rather than a raw IP protocol number like GRE's 47) is a deliberate design choice for compatibility** — UDP traffic on a specific port traverses load balancers, ECMP routing, and various middleboxes far more predictably than a raw IP protocol number does, echoing the same firewall/path-compatibility motivation seen in SSL/TLS VPN's design ([§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md)).
- **The VNI in VXLAN plays the same conceptual role as a VLAN ID** (segmenting the overlay into isolated logical networks) but at a scale VLANs' 12-bit tag can't reach — this is precisely why large multi-tenant cloud and container platforms use VXLAN/GENEVE rather than traditional VLANs for network segmentation at scale.

## 5. Hands-On

### 5.1 Creating a Basic GRE Tunnel on Linux

**Purpose:** Establish a plain (unencrypted) point-to-point GRE tunnel between two Linux hosts, demonstrating the core encapsulation mechanism independent of any encryption layer.

**Syntax:**

```bash
ip tunnel add <tunnel-name> mode gre remote <remote-public-ip> local <local-public-ip> ttl 255
ip addr add <tunnel-private-ip>/<prefix> dev <tunnel-name>
ip link set <tunnel-name> up
```

**Example usage and expected output:**

```bash
$ sudo ip tunnel add gre1 mode gre remote 203.0.113.20 local 203.0.113.10 ttl 255
$ sudo ip addr add 192.168.100.1/30 dev gre1
$ sudo ip link set gre1 up

$ ip addr show gre1
5: gre1@NONE: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1476 qdisc noqueue state UNKNOWN group default qlen 1000
    link/gre 203.0.113.10 peer 203.0.113.20
    inet 192.168.100.1/30 scope brd 192.168.100.3 scope global gre1
```

- `mode gre` explicitly selects GRE encapsulation (as opposed to other `ip tunnel` modes like `ipip` for plain IP-in-IP encapsulation).
- `mtu 1476` is smaller than a typical Ethernet MTU of 1500 — GRE's own header overhead (24 bytes for the base header) reduces the usable payload size, exactly the tunnel-MTU consideration raised generally in [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md).
- With no encryption layer applied, this tunnel is functional for encapsulation/reachability purposes but provides zero confidentiality — anyone capturing traffic on the path sees the original packet's contents in full once they parse the GRE header.

**Production usage example:** This exact `ip tunnel` command pattern is the basis for connecting two routers/gateways that need to exchange dynamic routing protocol traffic (which relies on multicast) across a network path that doesn't otherwise support multicast forwarding — GRE's tunnel presents as a simple point-to-point link that the routing protocol can run over normally.

**Common errors:** Deploying a bare GRE tunnel across the public internet under the mistaken assumption it provides any security — this is a genuine, recurring misconfiguration; GRE alone should never be the only protection for traffic crossing an untrusted network, and should be paired with IPsec whenever that's the case.

### 5.2 Layering IPsec Over an Existing GRE Tunnel

**Purpose:** Add encryption and authentication to a GRE tunnel by applying an IPsec transport-mode policy specifically to the GRE traffic between the two tunnel endpoints.

**Syntax:**

```ini
# strongSwan config protecting GRE traffic between the two tunnel endpoints
connections {
    gre-protection {
        local_addrs  = <local-public-ip>
        remote_addrs = <remote-public-ip>
        children {
            gre-over-ipsec {
                local_ts  = <local-public-ip>/32[gre]
                remote_ts = <remote-public-ip>/32[gre]
                mode      = transport
            }
        }
    }
}
```

**Example usage and expected output:**

```bash
$ sudo swanctl --load-all
loaded 1 connection, 0 unrouted
$ sudo swanctl --initiate --child gre-over-ipsec
CHILD_SA gre-over-ipsec{1} established
```

- `mode = transport` (not tunnel mode) is used here specifically because GRE has already done the encapsulation between the two gateways' own public IPs — IPsec only needs to protect that already-encapsulated GRE traffic between the same two endpoints, not encapsulate a further private-address packet itself.
- `[gre]` in the traffic selector restricts this IPsec policy to protecting GRE protocol traffic specifically, rather than all traffic between the two public IPs.

**Production usage example:** This is the standard "GRE over IPsec" pattern used when two network gateways need both dynamic routing protocol support (via GRE) and confidentiality/integrity (via IPsec) — common in enterprise WAN designs connecting branch offices where OSPF or similar needs to run natively across the link.

**Common errors:** Confusing transport mode and tunnel mode in this specific composition — using tunnel mode here would encapsulate the already-GRE-encapsulated packet inside yet another IP header unnecessarily, adding overhead without benefit, since GRE has already provided the encapsulation function tunnel mode would otherwise be needed for.

## 6. Production Usage Notes

- **GRE tunnel overhead (an additional ~24 bytes minimum) compounds with any further encapsulation (IPsec) applied on top**, making MTU/MSS clamping considerations from [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md) even more important for GRE-over-IPsec deployments than for a single-layer tunnel.
- **VXLAN and GENEVE overlays are largely invisible to the infrastructure engineer working at the application or Kubernetes level**, but understanding that pod-to-pod traffic in many CNI implementations is actually VXLAN-encapsulated demystifies otherwise-confusing packet captures showing UDP port 4789 (VXLAN's default port) traffic between node IPs that doesn't obviously correspond to any application traffic.
- **L2TP/IPsec remains supported by many operating systems as a built-in VPN client option** (requiring no separate app install), which is sometimes still chosen for exactly that convenience despite being a generally older, less-preferred technology compared to WireGuard or modern SSL/TLS VPN clients.

## 7. Security Considerations

- **A bare GRE tunnel provides zero confidentiality and only very weak (checksum-based, not cryptographic) integrity protection at best** — it must never be relied upon as a security boundary by itself when crossing any untrusted network; IPsec (or another encryption layer) is required whenever confidentiality/integrity actually matters.
- **GRE tunnel endpoints can be spoofed relatively easily without additional authentication**, since GRE itself has no strong built-in authentication mechanism — this is another reason GRE-over-IPsec (where IPsec's IKE-based mutual authentication protects the whole construct) is the production-appropriate pattern rather than plain GRE across untrusted paths.
- **VXLAN and GENEVE overlays are typically deployed within an already-trusted underlay network** (a single data center or cloud provider's internal network fabric) rather than across the public internet, which is why they typically don't include encryption by default — the trust boundary is assumed to already exist at the underlay level, an assumption that would be inappropriate if extended across an untrusted public network.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                                 | Resolution Path                                                                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| GRE tunnel interface is up, but no traffic flows | Firewall or NAT device on the path is blocking IP protocol 47 (GRE isn't a TCP/UDP port and some middleboxes drop it) | Confirm IP protocol 47 is explicitly allowed through any firewalls on the path; GRE can't traverse many strict NAT devices without special handling |
| Large packets fail across a GRE tunnel while small ones succeed | Tunnel MTU reduction from GRE header overhead (compounded further if IPsec is layered on top) | Lower the tunnel interface MTU or configure MSS clamping to account for the added encapsulation overhead |
| Dynamic routing protocol (OSPF/EIGRP) won't form an adjacency over a plain IPsec tunnel | IPsec tunnel mode alone doesn't carry the multicast traffic the routing protocol depends on | Use GRE over IPsec instead of plain IPsec tunnel mode, since GRE natively carries multicast/broadcast traffic |
| Kubernetes pod-to-pod traffic capture shows unexpected UDP port 4789 traffic between node IPs | This is expected VXLAN overlay encapsulation from the CNI plugin, not an anomaly | Confirm this is the CNI's normal overlay behavior; decode with a VXLAN-aware capture filter if deeper inspection is needed |

## 9. Best Practices

- Never deploy a bare, unencrypted GRE tunnel across an untrusted network path for anything beyond non-sensitive testing — pair it with IPsec whenever confidentiality or strong authentication matters.
- Explicitly account for GRE's (and any additional IPsec's) header overhead when setting tunnel interface MTU, rather than leaving default MTU values in place and discovering fragmentation issues reactively.
- Recognize VXLAN/GENEVE overlay traffic for what it is during packet-capture-based troubleshooting of container or data center overlay networks, rather than treating unexpected UDP traffic on overlay ports as suspicious or anomalous.

## 10. Common Anti-Patterns / Mistakes

- **Assuming any tunnel technology implies encryption by default** — GRE, VXLAN, and GENEVE are all encapsulation-only protocols with no inherent confidentiality guarantee, unlike IPsec or WireGuard.
- **Choosing plain IPsec tunnel mode for a site-to-site link that actually needs to run a multicast-dependent dynamic routing protocol across it**, then being confused when the routing protocol never forms an adjacency — GRE over IPsec is the correct pattern for this specific requirement.
- **Ignoring the compounding MTU overhead when layering multiple encapsulation protocols** (GRE plus IPsec, or VXLAN plus an outer VPN) and being surprised by fragmentation-related failures that proper MTU/MSS planning would have prevented.

## 11. Interview Questions

**🎯 Beginner:** _"Does GRE provide encryption?"_
**Model answer:** No — GRE is purely an encapsulation protocol that wraps one packet inside another to enable tunneling/reachability across a network, but it provides no confidentiality and only weak integrity protection at best. Encryption requires pairing GRE with a separate protocol like IPsec, commonly deployed as "GRE over IPsec."
_What the interviewer is probing for:_ A very common point of confusion — whether the candidate understands that "tunnel" and "encrypted" are not synonyms.

**🎯 Intermediate:** _"Why would you use GRE over IPsec instead of just plain IPsec tunnel mode for a site-to-site connection?"_
**Model answer:** Plain IPsec tunnel mode is built around encapsulating unicast IP traffic and doesn't natively carry multicast or broadcast traffic, or non-IP payloads. Many dynamic routing protocols (like OSPF) rely on multicast for neighbor discovery and updates, so if a site-to-site link needs to run such a protocol directly across the tunnel, GRE (which does support multicast/broadcast and arbitrary payloads) is used to carry that traffic, with IPsec then applied on top to encrypt the resulting GRE-encapsulated traffic — combining GRE's flexibility with IPsec's security.
_What the interviewer is probing for:_ Whether the candidate understands the specific, concrete reason this combination exists rather than treating it as an arbitrary "best of both" cliché.

**🎯 Senior:** _"You inherit a network with an existing plain GRE tunnel carrying production traffic across the public internet with no encryption. How do you assess and remediate this?"_
**Model answer:** I'd treat this as a real, likely-overlooked security gap — confidentiality-sensitive traffic crossing the public internet unencrypted is a meaningful exposure regardless of how long it's gone unnoticed. I'd first classify what traffic actually traverses the tunnel and how sensitive it is, to gauge urgency. I'd then plan adding IPsec protection over the existing GRE tunnel (transport mode, protecting the GRE-encapsulated traffic specifically between the two gateway public IPs) as a remediation, being careful to account for the additional MTU overhead this introduces and testing the change in a maintenance window given it's live production traffic. I'd also verify whether GRE's lack of authentication has any spoofing exposure on the network path in question before and after the fix.
_What the interviewer is probing for:_ Realistic operational judgment about remediating a discovered security gap in an existing production system without unnecessary disruption, not just theoretical knowledge of the fix.

**🎯 Architect:** _"How do overlay technologies like VXLAN relate to the VPN tunneling technologies covered elsewhere in this Part, and where does each fit in a modern cloud-native architecture?"_
**Model answer:** VXLAN and GENEVE solve a structurally similar problem to GRE/IPsec/WireGuard — encapsulating traffic to cross a network that doesn't natively support it — but for a different trust context and purpose: they're designed to build large-scale Layer 2-over-Layer 3 overlay networks *within* an already-trusted underlay (a single data center fabric, cloud provider's internal network, or Kubernetes cluster's node network), not to secure traffic crossing an untrusted public network. This is why they typically don't include encryption by default, unlike IPsec/WireGuard/SSL-TLS VPN, which exist specifically because the network being crossed is untrusted. In a modern cloud-native architecture, I'd expect VXLAN/GENEVE-style overlays handling pod-to-pod and service-to-service traffic within a cluster or VPC's trusted underlay, while VPN technologies (IPsec, WireGuard) handle the boundary crossings between genuinely separate trust domains — on-prem to cloud, or user device to private network.
_What the interviewer is probing for:_ Whether the candidate can correctly place multiple tunneling technologies along a trust-boundary axis rather than treating "tunneling protocol" as a single undifferentiated category.

## 12. Common Misconceptions

1. **"GRE is a VPN protocol."** GRE is a general-purpose encapsulation protocol with no inherent encryption; it becomes part of a VPN solution only when combined with an encryption layer like IPsec.
2. **"VXLAN and GRE solve the same problem."** GRE is a simple, general-purpose IP-in-IP-style encapsulation used for point-to-point tunnels; VXLAN specifically encapsulates Ethernet frames over UDP to build large-scale, multi-tenant Layer 2 overlay networks — different scale, purpose, and typical deployment context.
3. **"A tunnel interface being 'up' on both ends means traffic is definitely flowing correctly."** As with any tunneling technology in this Part, interface state confirms configuration was accepted, not that traffic is actually passing — GRE's lack of a keepalive/handshake mechanism by default makes this especially easy to overlook compared to IPsec or WireGuard, which have clearer SA/handshake state to check.
4. **"Overlay networks like VXLAN in Kubernetes are a security boundary."** VXLAN/GENEVE overlays typically exist for network segmentation and reachability within an already-trusted cluster/data-center underlay, not as an encryption or security boundary — a service mesh's mTLS (Part 13) or an explicit encryption layer is needed if encryption of pod-to-pod traffic itself is a requirement.

## 13. 🔑 Key Takeaways

- GRE encapsulates arbitrary payloads (including multicast, broadcast, and non-IP traffic) but provides no encryption or strong authentication on its own.
- "GRE over IPsec" is a specific, well-established pattern combining GRE's flexible encapsulation with IPsec's encryption, most commonly used to carry multicast-dependent dynamic routing protocols securely across a site-to-site link.
- VXLAN and GENEVE encapsulate Layer 2 frames over UDP to build large-scale overlay networks, foundational to modern data center, cloud, and container/Kubernetes networking — but they assume an already-trusted underlay and typically don't provide encryption by default.
- Tunnel MTU overhead compounds when multiple encapsulation layers are stacked (GRE plus IPsec, or an overlay plus a VPN), making proactive MTU/MSS planning increasingly important as more layers are added.
- Different tunneling technologies sit at different points along a trust-boundary axis — VPN technologies (IPsec, WireGuard, SSL/TLS VPN) secure crossings of untrusted networks, while overlay technologies (VXLAN, GENEVE) provide segmentation and reachability within an already-trusted underlay.

## 14. Related Concepts & What's Next

This section completes the tunneling-technology survey begun in [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md) and builds directly on the IPsec transport/tunnel mode mechanics from [§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md). The VXLAN/overlay networking concepts introduced here connect forward to the container and Kubernetes networking coverage in Part 13 ([§110](../Part13/Section-110-Part13-Container-Networking-Fundamentals-Bridge-Host-and-Overlay-Modes.md)–[§114](../Part13/Section-114-Part13-Cross-Reference-Where-Kubernetes-Specific-Networking-Continues-in-This-Repo.md)), where CNI plugin overlay modes are covered in their own dedicated context, and back to the SDN/overlay introduction in [§43](../Part5/Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md) from Part 5. [§98](Section-98-Part11-MPLS-Concepts-and-Where-It-Fits-in-Enterprise-WANs.md) immediately following shifts from tunneling protocols to enterprise WAN architecture, covering MPLS as another way large organizations have historically solved private, multi-site connectivity.

**Next Section:** [§98](Section-98-Part11-MPLS-Concepts-and-Where-It-Fits-in-Enterprise-WANs.md) — `Section-98-Part11-MPLS-Concepts-and-Where-It-Fits-in-Enterprise-WANs.md`
