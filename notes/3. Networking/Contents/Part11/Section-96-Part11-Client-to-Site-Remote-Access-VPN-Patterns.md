# Section 96 (Part 11): Client-to-Site (Remote Access) VPN Patterns

## 1. Definition

**Plain language:** A client-to-site VPN is the pattern most people actually mean when they say "I connected to the VPN" — an individual laptop or phone, running client software, tunneling into a private network from wherever it happens to be. Unlike a site-to-site VPN's permanent gateway-to-gateway link, this connection is per-user, per-session, and needs to work reliably from an unpredictable variety of networks.

**Precise definition:** A **client-to-site VPN** (also called a **remote-access VPN**) establishes a tunnel between an individual end-user device (the "client") and a gateway at the edge of a private network (the "site"), letting that one device reach private network resources as if it were physically present on that network. This is architecturally distinct from the site-to-site pattern in [§95](Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md) in two key ways: first, every individual client device is its own tunnel endpoint requiring its own client software, credentials, and often per-user authentication (frequently integrated with SSO/MFA); second, clients connect and disconnect dynamically and from unpredictable, changing network locations (home, office, mobile, travel), rather than a gateway with a fixed, known public IP. A central design decision is **split tunnel vs. full tunnel** routing: a **split-tunnel** configuration routes only specific private-network CIDRs through the VPN while all other traffic (general internet browsing) uses the client's normal local internet connection directly, minimizing gateway bandwidth load and latency for non-private traffic; a **full-tunnel** configuration routes *all* of the client's traffic — including general internet access — through the VPN gateway, which centralizes traffic for inspection/filtering/compliance at the cost of added latency and gateway bandwidth for every byte the client sends anywhere. Remote-access VPNs are commonly built on SSL/TLS VPN products ([§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md)) specifically for their firewall-traversal reliability across the unpredictable networks clients connect from, though IPsec (IKEv2 with EAP authentication) and WireGuard ([§94](Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md)) are also common, particularly WireGuard for its lightweight client footprint and strong performance.

> 💡 **Tip:** The single most consequential decision in designing a remote-access VPN deployment is split tunnel vs. full tunnel — this isn't a minor configuration detail, it's a policy decision with direct security, performance, and cost implications that should be made deliberately, not left at a product's default.

## 2. Why This Matters

- **Client-to-site VPN is the most common way engineers, on-call staff, and remote employees reach private infrastructure that isn't otherwise internet-exposed** — access to a private Kubernetes API server, an internal admin panel, or a bastion host frequently depends on this pattern working reliably.
- **Split tunnel vs. full tunnel is a decision with real, opposing trade-offs that organizations get wrong in both directions** — full tunnel unnecessarily burdens gateway bandwidth and adds latency for traffic that never needed to touch the private network at all; overly permissive split tunnel can under-protect traffic an organization actually wanted centrally inspected.
- **Client device diversity and network unpredictability make remote-access VPN a disproportionately high-support-burden system** compared to site-to-site VPN's relatively static, controlled endpoints — understanding common client-side failure modes (this section's troubleshooting table) directly reduces that burden.
- **Modern remote-access VPN increasingly intersects with zero-trust network access (ZTNA) models** that de-emphasize or replace broad VPN-granted network reachability with narrower, per-application, identity-verified access — understanding traditional client-to-site VPN is the necessary baseline for evaluating that shift, connecting back to the zero-trust principles in [§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md).
- **This is one of the most universally relevant sections in Part 11 for day-to-day engineering work** — nearly every infrastructure engineer personally uses a client-to-site VPN routinely, making its mechanics directly applicable troubleshooting knowledge, not just architectural theory.

## 3. Prerequisites and Dependencies

This section directly contrasts with the site-to-site pattern from [§95](Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md) and assumes that section's gateway-to-gateway model as a point of comparison. It builds on the SSL/TLS VPN vs. IPsec comparison from [§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md), since that comparison's firewall-traversal argument is most directly relevant to exactly this client-to-site scenario, and on WireGuard's client configuration model from [§94](Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md). Basic routing table familiarity ([§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)) is assumed for understanding how split-tunnel routes are actually implemented on a client. This section's zero-trust framing connects to [§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) from Part 10, which is worth reviewing for full context on the broader shift away from network-location-based trust models.

## 4. Architecture / Conceptual Diagram

```text
   Split-tunnel remote access:                    Full-tunnel remote access:

   Client laptop                                  Client laptop
        │                                               │
        ├──► 10.0.0.0/16 (private) ──► VPN Gateway      ├──► ALL traffic ──► VPN Gateway
        │       (routed through tunnel)                 │       (both private CIDR and
        │                                               │        general internet routed
        └──► 0.0.0.0/0 (internet) ──► local ISP         │        through the gateway)
                (direct, not through VPN)                └──► Gateway forwards internet
                                                              traffic onward (NAT'd),
                                                              or applies inspection/
                                                              filtering policy first

   Both patterns share:
   - Per-user authentication (often SSO/MFA-integrated) before tunnel establishment
   - A client running VPN software that creates a local virtual tunnel interface
   - Dynamic, unpredictable client-side network location and public IP
```

- **The routing table entries a client's VPN software installs are the actual mechanism enforcing split-tunnel vs. full-tunnel behavior** — this is directly inspectable with the same `ip route show` technique from [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md), and is the ground truth for what a given VPN connection is actually doing, independent of what its configuration UI claims.
- **Per-user authentication integrated with SSO/MFA is a structural feature of most modern remote-access VPN products** that has no real equivalent in the site-to-site pattern, since a site-to-site tunnel authenticates the *gateway*, not an individual human — this is a meaningful architectural difference beyond just "one is for individuals and one is for whole networks."
- **A full-tunnel client's general internet traffic exits from the VPN gateway's location and egress IP**, not the client's own local network — this has real, visible effects (geolocation of the client's apparent IP shifts to the gateway's location, and the gateway's own internet bandwidth becomes a shared resource across every connected full-tunnel client).

## 5. Hands-On

### 5.1 Configuring Split-Tunnel Routing in a WireGuard Client

**Purpose:** Demonstrate the concrete configuration mechanism that determines split-tunnel vs. full-tunnel behavior for a remote-access client.

**Syntax:**

```ini
# Split tunnel: AllowedIPs limited to private ranges only
[Peer]
PublicKey = <gateway public key>
AllowedIPs = 10.0.0.0/16, 172.16.0.0/12
Endpoint = vpn.example.com:51820

# Full tunnel: AllowedIPs covers everything
[Peer]
PublicKey = <gateway public key>
AllowedIPs = 0.0.0.0/0
Endpoint = vpn.example.com:51820
```

**Example usage and expected output:**

```bash
$ sudo wg-quick up client
[#] wg setconf client /dev/fd/63
[#] ip -4 route add 10.0.0.0/16 dev client
[#] ip -4 route add 172.16.0.0/12 dev client
```

- With the split-tunnel `AllowedIPs`, only the two listed private ranges get a route through the tunnel interface — general internet traffic (e.g., a route to `8.8.8.8`) is untouched and continues using the client's normal default route.
- With `AllowedIPs = 0.0.0.0/0` (full tunnel), WireGuard's `wg-quick` script replaces the client's default route entirely, sending every packet — private and internet-bound alike — through the tunnel interface.

**Production usage example:** Organizations that need to centrally log or filter all remote-employee internet traffic (a compliance or security requirement in some regulated industries) deliberately choose the full-tunnel `0.0.0.0/0` configuration despite its bandwidth and latency cost, accepting that trade-off as the point of the control.

**Common errors:** Accidentally configuring `AllowedIPs = 0.0.0.0/0` when split-tunnel behavior was actually intended (a very easy typo/misunderstanding, since it's just one line) — the practical symptom is a user reporting their general internet browsing has become slow or their apparent IP/location has changed after connecting to what they thought was a narrow-scope VPN.

### 5.2 Diagnosing a Client That Can't Reach a Specific Private Resource

**Purpose:** Isolate whether a remote-access VPN client's connectivity failure is a tunnel problem, a routing/split-tunnel scope problem, or a downstream security-control problem.

**Syntax:**

```bash
ip route get <target-private-ip>
nc -zv <target-private-ip> <port>
```

**Example usage and expected output:**

```bash
$ ip route get 10.0.5.20
10.0.5.20 via 10.8.0.1 dev wg0 src 10.8.0.2

$ nc -zv 10.0.5.20 443
nc: connect to 10.0.5.20 port 443 (tcp) failed: Connection timed out
```

- `ip route get` confirms the client's routing table *would* send traffic for this destination through the tunnel — if this instead showed the client's normal internet-facing interface, the fix is a routing/`AllowedIPs`/split-tunnel scope issue, not a downstream problem.
- Given the route is correct but the connection still times out, the next suspects are a firewall/security-group rule on the target resource's side, or the target simply not listening on that port — not the VPN tunnel itself, which has already been confirmed to be correctly routing this traffic.

**Production usage example:** This two-step check is the standard remote-access VPN support triage sequence: confirm the client's routing table sends the traffic into the tunnel at all, then confirm actual reachability — separating "the VPN doesn't know about this destination" from "the VPN routes it correctly but something downstream is blocking it."

**Common errors:** Assuming any connectivity failure while connected to a VPN must be a VPN problem, when the VPN's own routing is often confirmed correct and the actual blocker is a security group, host firewall, or the target service being down — this class of assumption wastes significant troubleshooting time redirected at the wrong layer.

## 6. Production Usage Notes

- **Per-user, per-device VPN client provisioning and revocation needs an explicit lifecycle process** — when an employee leaves or a device is lost/compromised, their VPN access needs immediate, reliable revocation; this is a common integration point with SSO/identity provider offboarding automation rather than a manual, VPN-specific process.
- **Remote-access VPN gateway capacity planning must account for concurrent connected-user count and their aggregate bandwidth**, especially under a full-tunnel policy where every connected user's entire internet traffic adds to gateway load — a gateway sized for a normal workday can be caught off guard by unusual demand spikes (e.g., a company-wide remote event).
- **MFA/SSO integration at VPN connection time is now a widely expected baseline control**, not an advanced feature — a remote-access VPN authenticated by password alone is a meaningfully weaker control than one requiring a second factor, given how frequently password-only credentials are compromised through unrelated breaches.

## 7. Security Considerations

- **A compromised remote-access VPN credential potentially grants an attacker the same private-network reachability as the legitimate user** — this is precisely the scenario zero-trust architecture ([§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)) aims to limit the blast radius of, by not treating "connected via VPN" as sufficient grounds for broad implicit trust.
- **Split-tunnel configurations reduce the VPN gateway's ability to inspect or filter a client's general internet traffic** — this is a deliberate, often correct trade-off for performance, but it should be a conscious security-policy decision, not an unexamined default.
- **Client device posture (up-to-date OS, endpoint security software, disk encryption) is increasingly treated as a prerequisite for VPN access** in security-mature organizations, since an outdated or compromised client device connecting into a private network is itself a meaningful risk vector independent of the VPN tunnel's own cryptographic soundness.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                                 | Resolution Path                                                                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| VPN connects, but a specific private resource is unreachable | The resource's CIDR isn't included in the client's split-tunnel `AllowedIPs`/routes | Confirm with `ip route get`; add the missing CIDR to the tunnel's routed ranges |
| General internet browsing becomes slow/unusable after connecting | An unintended full-tunnel configuration is routing all traffic through a bandwidth-constrained gateway | Verify `AllowedIPs`/routing scope matches the intended split-tunnel or full-tunnel policy |
| VPN client fails to connect only from certain networks (hotels, some countries) | The client's VPN protocol (commonly IPsec) is being blocked by that network's firewall | Offer or switch to an SSL/TLS-based or WireGuard-over-common-port fallback client configuration |
| User's VPN access still works after they've left the organization | VPN credential/certificate revocation wasn't included in the offboarding process | Integrate VPN access revocation directly into SSO/identity-provider offboarding automation |

## 9. Best Practices

- Make the split-tunnel vs. full-tunnel decision deliberately and document it as policy, rather than accepting a VPN product's default configuration unexamined.
- Integrate remote-access VPN authentication with existing SSO/MFA infrastructure rather than maintaining a separate, VPN-specific credential store that's easy to forget during offboarding.
- Provide a firewall-traversal-friendly fallback option (SSL/TLS-based VPN, or WireGuard configured on a common port) for users who routinely connect from restrictive network environments.

## 10. Common Anti-Patterns / Mistakes

- **Leaving split-tunnel/full-tunnel configuration at whatever a VPN product defaults to**, without evaluating whether that default matches the organization's actual security and performance needs.
- **Treating VPN credential revocation as a manual, easily-forgotten step in offboarding** rather than an automated part of the identity-provider deprovisioning workflow.
- **Assuming any connectivity issue while VPN-connected is automatically a VPN problem**, without first confirming (via routing table inspection) whether the VPN is even involved in the specific traffic path failing.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between split-tunnel and full-tunnel VPN configuration?"_
**Model answer:** Split tunnel routes only specific private-network traffic through the VPN, letting general internet traffic use the client's normal local connection directly. Full tunnel routes all of the client's traffic — private and internet-bound alike — through the VPN gateway, which is useful for centralized traffic inspection/filtering but adds latency and gateway bandwidth cost for every byte the client sends anywhere.
_What the interviewer is probing for:_ A clear, correct definition of a very commonly-referenced but sometimes loosely-understood configuration distinction.

**🎯 Intermediate:** _"Why might an organization choose an SSL/TLS-based remote-access VPN over an IPsec-based one?"_
**Model answer:** Remote-access clients connect from unpredictable, often restrictive network environments (hotels, airports, various countries' networks), and IPsec's ESP/UDP-500/4500 traffic is more frequently blocked by such networks than ordinary TLS-over-443 traffic. An SSL/TLS-based VPN client is far more likely to successfully connect from any given network environment, which matters disproportionately for remote-access scenarios compared to site-to-site connectivity between known, fixed, controlled endpoints.
_What the interviewer is probing for:_ Direct application of the [§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md) comparison to a realistic remote-access scenario, showing the candidate connects theory to practical deployment choices.

**🎯 Senior:** _"A remote employee reports they can VPN in successfully but can't reach a newly-launched internal service, while everyone else in the office can reach it fine. What's your diagnostic approach?"_
**Model answer:** I'd first check the client's actual routing table (`ip route get` against the new service's IP) to see whether the VPN is even routing traffic for that destination into the tunnel at all — if the new service's subnet wasn't included when the split-tunnel `AllowedIPs`/routes were originally configured, this is a routing-scope gap, not a broader VPN failure, and it would specifically affect only VPN users while leaving office users (already on the private network directly) unaffected, matching the reported symptom exactly. If the route is correct, I'd next check whether a security group or NACL on the new service explicitly allows the VPN client subnet, since a newly-launched service's security rules sometimes only account for the office network range and not the VPN's separate client address pool.
_What the interviewer is probing for:_ The ability to reason about why a symptom affects VPN users specifically and not office users, narrowing the investigation efficiently rather than treating it as a generic "VPN is broken" report.

**🎯 Architect:** _"Your organization wants to reduce reliance on broad-access remote VPN in favor of a more zero-trust-aligned access model. How would you approach this transition?"_
**Model answer:** I'd start by inventorying what private resources remote-access VPN users actually need, and for how many of those a narrower, per-application zero-trust access proxy (rather than broad network-layer VPN reachability) could substitute — many internal web applications and APIs can be fronted by an identity-aware proxy that authenticates and authorizes each request individually, without granting the requesting device any broader network reachability at all. I'd retain VPN for cases genuinely requiring broad network-layer access (direct database connections, legacy protocols that don't fit a proxy model, or full private-network debugging access for infrastructure engineers) while migrating the bulk of routine application access to the narrower model. Throughout, I'd pair this with the zero-trust segmentation principles from [§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md), ensuring that even where VPN remains, "connected" doesn't imply broad implicit trust to everything reachable on the private network.
_What the interviewer is probing for:_ Strategic, incremental thinking about a real industry trend (VPN toward ZTNA) rather than an all-or-nothing "rip out the VPN" answer, and recognition that VPN and zero-trust access aren't mutually exclusive during a transition.

## 12. Common Misconceptions

1. **"Full tunnel is always more secure than split tunnel because it 'protects more' traffic."** Full tunnel centralizes traffic for inspection, which is a real benefit for specific compliance/security goals, but it isn't unconditionally "more secure" — it adds real gateway bandwidth exposure and latency cost, and the right choice depends on the organization's actual policy goals, not a blanket security ranking.
2. **"Client-to-site and site-to-site VPN are just the same technology used at different scales."** They share underlying tunneling technology but differ structurally in per-user authentication, dynamic/unpredictable client network location, and per-device software requirements — meaningfully different operational and security considerations apply to each.
3. **"Once VPN client software shows 'connected,' all intended traffic is flowing through the tunnel as expected."** The client's actual routing table — not the connection-status indicator — determines what traffic really goes through the tunnel; a "connected" full-tunnel client with a routing misconfiguration can still leak specific traffic outside the tunnel.
4. **"Remote-access VPN alone is a complete, sufficient security control for protecting internal resources."** VPN provides network reachability; it does not replace application-level authentication/authorization, device posture checks, or the zero-trust segmentation controls that limit what a connected-but-potentially-compromised client can actually do.

## 13. 🔑 Key Takeaways

- Client-to-site VPN differs structurally from site-to-site VPN in requiring per-user client software, per-user authentication, and tolerance for unpredictable client network locations.
- The split-tunnel vs. full-tunnel decision is a deliberate policy choice with real security, performance, and cost trade-offs — never leave it at an unexamined default.
- A client's actual routing table (`ip route get`/`ip route show`) is the ground truth for what traffic a VPN connection really carries, independent of what the client UI or configuration file claims.
- Firewall/NAT traversal reliability from unpredictable client networks is a primary driver toward SSL/TLS-based or common-port WireGuard configurations for remote-access deployments.
- VPN credential lifecycle (provisioning and especially revocation) needs to be tightly integrated with identity-provider/SSO offboarding automation, not treated as a separate manual process.

## 14. Related Concepts & What's Next

This section directly contrasts with [§95](Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md)'s gateway-to-gateway pattern and builds on the SSL/TLS-vs-IPsec trade-offs from [§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md) and WireGuard's client model from [§94](Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md). Its zero-trust/ZTNA discussion connects to [§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) from Part 10. [§97](Section-97-Part11-GRE-and-Other-Tunneling-Protocols.md) immediately following shifts focus away from encrypted VPN tunnels specifically toward the broader family of tunneling protocols (like GRE) that solve encapsulation problems without necessarily providing encryption.

**Next Section:** [§97](Section-97-Part11-GRE-and-Other-Tunneling-Protocols.md) — `Section-97-Part11-GRE-and-Other-Tunneling-Protocols.md`
