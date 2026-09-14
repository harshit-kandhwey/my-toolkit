# Section 92 (Part 11): IPsec: AH/ESP, Tunnel vs. Transport Mode, IKE Phases

## 1. Definition

**Plain language:** IPsec is the industry-standard toolbox for building encrypted, authenticated tunnels directly at the IP layer. It's not one protocol but a suite of them working together: one to negotiate and manage the cryptographic keys, and one or two others to actually protect the packets once keys are in place. It's the technology underneath the vast majority of enterprise and cloud site-to-site VPN connections, including every major cloud provider's managed VPN gateway service.

**Precise definition:** **IPsec (Internet Protocol Security)** is a suite of protocols, standardized primarily in RFC 4301 and related RFCs, that provides confidentiality, integrity, and authentication for IP traffic. It has two core data-protection protocols — **AH (Authentication Header)**, which authenticates and integrity-protects a packet but does **not** encrypt its payload, and **ESP (Encapsulating Security Payload)**, which provides encryption in addition to authentication and integrity, making ESP the overwhelmingly more common choice in practice since confidentiality is almost always required. Either protocol can operate in **transport mode**, which protects only the original packet's payload while leaving the original IP header intact (used for host-to-host protection where both endpoints are the actual communicating hosts), or **tunnel mode**, which encapsulates the *entire* original packet — including its IP header — inside a new outer IP packet, which is what makes tunnel mode the mode used for gateway-to-gateway VPNs, since the outer header carries the gateways' public IPs while the inner, hidden header carries the original private addresses. Before any data protection happens, **IKE (Internet Key Exchange)**, currently at version 2 (**IKEv2**, RFC 7296) in modern deployments, runs a two-phase negotiation: **Phase 1 (IKE_SA_INIT / IKE_AUTH in IKEv2)** establishes a secure, authenticated channel between the two gateways themselves, and **Phase 2 (CREATE_CHILD_SA in IKEv2)** uses that secure channel to negotiate the actual **IPsec Security Associations (SAs)** — the specific keys and algorithms that will protect the real data traffic.

> 💡 **Tip:** Nearly every cloud provider's "Site-to-Site VPN" product (AWS Site-to-Site VPN, Azure VPN Gateway, GCP Cloud VPN) is IPsec with IKEv2 under the hood, configured through a managed console/API rather than raw `strongswan` config files — understanding IPsec's mechanics directly transfers to correctly configuring and troubleshooting all of them.

## 2. Why This Matters

- **IPsec is the de facto standard for site-to-site VPNs across virtually every enterprise network, cloud provider, and network hardware vendor** — it's the one VPN technology an infrastructure engineer is almost guaranteed to encounter regardless of which cloud or vendor ecosystem they work in.
- **IKE Phase 1/Phase 2 failures are the most common IPsec troubleshooting scenario**, and diagnosing them correctly requires understanding which phase is failing — a Phase 1 failure means the gateways can't even authenticate to each other, while a Phase 2 failure means they authenticated fine but couldn't agree on how to protect the actual data traffic. These have completely different root causes and fixes.
- **AH vs. ESP and tunnel vs. transport mode are not academic distinctions** — getting them wrong (e.g., trying to use AH through a NAT device, which breaks AH's integrity check) causes real, hard-to-diagnose connectivity failures that only make sense once the underlying mechanics are understood.
- **Cloud VPN gateway configuration screens directly expose IPsec/IKE parameters** (Phase 1/Phase 2 encryption algorithms, DH group, lifetime) that must match on both sides of a tunnel — misconfiguring or mismatching these is one of the single most common causes of "the VPN tunnel won't come up" tickets.
- **IPsec underpins security-conscious enterprise interconnects** where compliance or contractual requirements mandate specific, auditable cryptographic standards, making IPsec's maturity and standardization a deliberate choice over newer alternatives in some environments.

## 3. Prerequisites and Dependencies

This section builds directly on the VPN fundamentals and tunneling concepts introduced in [§91](Section-91-Part11-VPN-Fundamentals-Why-Tunnel-Traffic.md), and assumes that general encapsulation model as a starting point. It also assumes familiarity with public-key/asymmetric cryptography concepts and certificate-based authentication from the TLS coverage in [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md), since IKE's authentication step (using either pre-shared keys or certificates) parallels TLS's own handshake authentication conceptually, even though the protocols are unrelated. Basic IP addressing and NAT familiarity ([§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md)) is assumed as well, since NAT traversal (NAT-T) is a real, frequently-encountered complication when IPsec gateways sit behind NAT devices. This section is a deep dive into one specific VPN technology; [§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md) immediately following contrasts IPsec against the SSL/TLS VPN alternative, and [§95](Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md) covers how IPsec tunnels are deployed in practice as managed cloud gateway services.

## 4. Architecture / Conceptual Diagram

```text
   IKE Phase 1 (establish a secure channel between gateways):

   Gateway A ──── IKE_SA_INIT (DH key exchange, algorithm negotiation) ────► Gateway B
   Gateway A ◄─── IKE_AUTH (mutual authentication: PSK or certificates) ──── Gateway B
             │
             ▼
     A secure, authenticated "IKE SA" channel now exists between the gateways

   IKE Phase 2 (negotiate the actual data-protection SAs):

   Gateway A ──── CREATE_CHILD_SA (propose ESP/AH, encryption, lifetime) ──► Gateway B
   Gateway A ◄─── CREATE_CHILD_SA (accept/negotiate parameters) ──────────── Gateway B
             │
             ▼
     One or more "IPsec SAs" now exist — the actual keys/algorithms protecting data

   Tunnel mode ESP data packet:

   ┌─────────────┬─────────────┬───────────────────────────────────┐
   │ New Outer IP│  ESP Header │  Original IP Packet (encrypted:    │
   │ Header      │             │  original header + payload)        │
   │ (gateway     │             │                                    │
   │  public IPs)│             │                                    │
   └─────────────┴─────────────┴───────────────────────────────────┘
        visible                         hidden inside ESP encryption
```

- **The two IKE phases exist because renegotiating a full authenticated channel for every data-protection SA would be wasteful** — Phase 1 does the expensive authentication once, and Phase 2 can cheaply negotiate (and later rekey) multiple data SAs under that established channel.
- **Tunnel mode's outer IP header uses the gateways' own public IPs, while the original packet's private-IP header is fully hidden inside the encrypted payload** — this is precisely what makes tunnel mode suitable for gateway-to-gateway VPNs connecting private networks that use non-routable addressing.
- **ESP's header sits between the outer and inner IP headers**, carrying the Security Parameter Index (SPI) that tells the receiving gateway which SA (and therefore which keys/algorithms) to use to decrypt and verify the packet.

## 5. Hands-On

### 5.1 Configuring a strongSwan IPsec Tunnel

**Purpose:** Establish a basic site-to-site IPsec tunnel between two gateways using `strongswan`, the most common open-source IPsec implementation on Linux.

**Syntax:**

```ini
# /etc/swanctl/swanctl.conf
connections {
    site-to-site {
        local_addrs  = <local-public-ip>
        remote_addrs = <remote-public-ip>
        local {
            auth = psk
        }
        remote {
            auth = psk
        }
        children {
            net-net {
                local_ts  = <local-private-cidr>
                remote_ts = <remote-private-cidr>
                mode      = tunnel
                esp_proposals = aes256gcm16-prfsha384-ecp384
            }
        }
        version = 2
        proposals = aes256-sha384-ecp384
    }
}
```

**Example usage and expected output:**

```bash
$ sudo swanctl --load-all
loaded 1 connection, 0 unrouted

$ sudo swanctl --initiate --child net-net
initiating IKE_SA site-to-site[1] to <remote-public-ip>
generating IKE_SA_INIT request ...
received IKE_SA_INIT response ...
authentication of '<local-public-ip>' (myself) successful
authentication of '<remote-public-ip>' successful
IKE_SA site-to-site[1] established
CHILD_SA net-net{1} established
```

- `version = 2` selects IKEv2, the modern standard over legacy IKEv1, which has known weaknesses and slower negotiation.
- `mode = tunnel` explicitly selects tunnel mode, encapsulating the full original packets between `local_ts`/`remote_ts` (the private CIDRs each side is authorized to route through this tunnel).
- `esp_proposals` and `proposals` list the Phase 2 and Phase 1 cryptographic algorithms respectively — **both sides must have at least one matching proposal or negotiation fails outright.**

**Production usage example:** This exact `swanctl` configuration pattern is the basis for connecting an on-prem data center to a cloud VPC when a managed cloud VPN gateway on the other end presents standard IPsec/IKEv2 parameters — the on-prem side is frequently a Linux box or dedicated appliance running strongSwan against the cloud provider's public gateway IP.

**Common errors:** Mismatched `proposals`/`esp_proposals` between the two sides (e.g., one side offers `aes256-sha384-ecp384` and the other only accepts `aes128-sha256-modp2048`) causes an immediate, silent negotiation failure with no data ever flowing — always confirm both sides' configured algorithm lists have at least one entry in common.

### 5.2 Diagnosing IKE Phase 1 vs. Phase 2 Failures

**Purpose:** Distinguish whether a non-functional tunnel is failing during authentication (Phase 1) or during data-SA negotiation (Phase 2), since the fixes differ completely.

**Syntax:**

```bash
sudo swanctl --list-sas
journalctl -u strongswan -f
```

**Example usage and expected output:**

```bash
$ sudo swanctl --list-sas
site-to-site: #1, ESTABLISHED, IKEv2, ...
  local  '<local-public-ip>'
  remote '<remote-public-ip>'
  net-net: #1, reqid 1, INSTALLED, TUNNEL, ESP:AES_GCM_16-256
    local  <local-private-cidr>
    remote <remote-private-cidr>
```

- `ESTABLISHED` on the IKE_SA line confirms Phase 1 succeeded (mutual authentication worked); `INSTALLED` on the child SA confirms Phase 2 succeeded and the actual data-protection keys are in place.
- If the IKE_SA line is missing entirely or shows a failed/retrying state, the problem is in Phase 1 — check pre-shared key or certificate mismatches, and confirm UDP 500/4500 reachability between the gateways.
- If the IKE_SA is `ESTABLISHED` but no child SA appears, Phase 1 succeeded and the problem is isolated to Phase 2 — check `local_ts`/`remote_ts` CIDR mismatches or ESP proposal mismatches.

**Production usage example:** This distinction is the first thing an experienced network engineer checks on any "VPN tunnel down" ticket, since it immediately narrows the investigation from "check everything" to "check authentication config" or "check traffic selector/algorithm config" specifically.

**Common errors:** Confusing a Phase 2 traffic-selector mismatch (where `local_ts`/`remote_ts` CIDRs on each side don't correspond to what the other side expects) with a routing problem — the tunnel can be fully `ESTABLISHED`/`INSTALLED` yet still pass no traffic for a specific subnet if that subnet wasn't included in the negotiated traffic selectors.

## 6. Production Usage Notes

- **NAT traversal (NAT-T) is a common real-world complication**: if either IPsec gateway sits behind a NAT device, ESP's own integrity protections can be broken by the NAT's address rewriting, so IKEv2 automatically detects NAT presence and encapsulates ESP inside UDP (typically port 4500) to survive translation — this is why IPsec deployments commonly need both UDP 500 and UDP 4500 open.
- **SA lifetimes and rekeying happen automatically and transparently** when configured correctly, refreshing keys periodically without dropping the tunnel — but mismatched lifetime values between the two sides can cause one side to rekey while the other still expects the old SA, producing intermittent, hard-to-reproduce tunnel drops.
- **Dead Peer Detection (DPD)** is a standard IKEv2 keepalive mechanism that detects a genuinely unreachable peer (versus temporary packet loss) and triggers tunnel teardown/rebuild — disabling or misconfiguring DPD timers is a common cause of tunnels that "look up" in configuration but have actually gone stale.

## 7. Security Considerations

- **Pre-shared keys (PSK) are simpler to configure than certificate-based authentication but scale and rotate worse** — a leaked PSK compromises the tunnel's authentication entirely and must be manually rotated on both sides simultaneously, whereas certificate-based authentication supports proper revocation and per-gateway identity.
- **AH is rarely the right choice in modern deployments** — since it provides no encryption, and its integrity protection over the (potentially NAT-rewritten) IP header makes it fundamentally incompatible with NAT traversal, ESP (with encryption) is the standard choice for virtually all practical VPN scenarios today.
- **Legacy IKEv1 and weak Diffie-Hellman groups (e.g., DH Group 2/MODP-1024) should be actively disabled**, mirroring the same "curate your cryptographic parameters, don't rely on old defaults" principle covered for TLS cipher suites in [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) — modern IPsec deployments should standardize on IKEv2 with strong DH groups (14+, or elliptic-curve groups) and AES-GCM.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                                 | Resolution Path                                                                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Tunnel never establishes; no IKE_SA appears at all | Phase 1 failure — mismatched PSK/certificates, or UDP 500/4500 blocked by a firewall en route | Verify pre-shared key/certificate config matches exactly on both sides; confirm UDP 500 and 4500 reachability |
| IKE_SA shows established, but no child SA / traffic doesn't flow | Phase 2 failure — mismatched ESP proposals or traffic selector (local_ts/remote_ts) CIDRs | Compare Phase 2 algorithm proposals and traffic selector CIDRs on both sides for an exact match |
| Tunnel works, then drops intermittently every few hours | Mismatched SA lifetime/rekey timers between the two gateways | Align rekey/lifetime values on both sides; verify DPD keepalive settings are consistent |
| Tunnel up, but traffic only flows to some private subnets, not others | Traffic selectors (Phase 2 `local_ts`/`remote_ts`) don't cover the missing subnet | Add the missing CIDR to the traffic selector configuration and re-negotiate the child SA |

## 9. Best Practices

- Standardize on IKEv2 with ESP, AES-GCM, and modern Diffie-Hellman groups across all new IPsec deployments; avoid IKEv1 and AH except where legacy interoperability strictly requires them.
- Explicitly configure and document matching SA lifetimes and DPD/keepalive parameters on both tunnel endpoints rather than relying on each side's independent defaults, which frequently don't match.
- Use `swanctl --list-sas` (or the cloud provider's equivalent tunnel status view) as the first diagnostic step to distinguish Phase 1 from Phase 2 failures before investigating further.

## 10. Common Anti-Patterns / Mistakes

- **Leaving legacy IKEv1 or weak DH groups enabled "just in case" a legacy peer needs them**, when the actual peer set is known and modern — this needlessly weakens the tunnel's cryptographic posture for no real compatibility benefit.
- **Debugging a "broken tunnel" without first checking whether the failure is in Phase 1 or Phase 2** — jumping straight to packet captures or firewall rule audits without this basic triage step wastes significant time compared to checking `swanctl --list-sas` first.
- **Forgetting NAT-T implications when a gateway sits behind NAT** and troubleshooting ESP connectivity issues as if both endpoints have unmediated public IP reachability, when UDP 4500 encapsulation is actually required.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between AH and ESP in IPsec?"_
**Model answer:** AH (Authentication Header) provides integrity and authentication for a packet but does not encrypt the payload — the data is still readable by an observer, just tamper-evident. ESP (Encapsulating Security Payload) provides both encryption and integrity/authentication, making it the practical default for essentially all modern VPN use cases since confidentiality is almost always a requirement.
_What the interviewer is probing for:_ Whether the candidate knows encryption is ESP's job, not AH's — a very common point of confusion.

**🎯 Intermediate:** _"Explain the two phases of IKE and why IPsec needs both."_
**Model answer:** Phase 1 establishes a secure, mutually authenticated channel between the two gateways themselves (via a Diffie-Hellman exchange and authentication using PSK or certificates), producing an IKE SA. Phase 2 then uses that already-secure channel to negotiate the actual IPsec SAs — the specific keys, ciphers, and traffic selectors that will protect real data traffic, producing one or more child SAs. Splitting these lets the expensive authenticated-channel setup happen once, while Phase 2 can cheaply negotiate or rekey multiple data SAs without repeating full authentication each time.
_What the interviewer is probing for:_ An accurate mental model of IKE's two-phase design, since this is central to correctly diagnosing any real IPsec tunnel failure.

**🎯 Senior:** _"A site-to-site IPsec tunnel between your data center and a cloud VPC shows as established, but traffic to one specific subnet never arrives while others work fine. What do you check?"_
**Model answer:** Given the tunnel is established overall, Phase 1 is clearly fine, so I'd focus on Phase 2 traffic selectors — the `local_ts`/`remote_ts` (or the cloud provider's equivalent tunnel/route configuration) may simply not include that specific subnet's CIDR, meaning no child SA exists to protect traffic for it even though other subnets' SAs are fine. I'd check the negotiated traffic selectors on both sides for an exact CIDR match, and separately verify the routing table actually directs that subnet's traffic toward the tunnel interface in the first place, since a routing gap and a traffic-selector gap produce similar symptoms but need different fixes.
_What the interviewer is probing for:_ The ability to reason precisely about IPsec's per-SA traffic-selector model rather than treating "the tunnel" as a single monolithic on/off construct.

**🎯 Architect:** _"You need to connect an on-prem data center to a multi-region cloud footprint with redundant IPsec tunnels for high availability. What design considerations matter most?"_
**Model answer:** I'd deploy redundant tunnels per site (at minimum an active/active pair to each cloud region's VPN gateway) and use dynamic routing (BGP, [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) over the tunnels rather than static traffic-selector-based routing, so that a tunnel failure triggers automatic route withdrawal and failover rather than a manual reconfiguration. I'd standardize cryptographic parameters (IKEv2, ESP with AES-GCM, matching DH groups and SA lifetimes) across every tunnel to avoid the mismatch failures that are the most common IPsec operational issue, and ensure DPD/keepalive settings are tuned consistently so failover is detected promptly. I'd also monitor each tunnel's IKE/child SA state continuously, since a silently-degraded tunnel (established but not passing expected traffic) is a more dangerous failure mode than an obviously-down one that immediately triggers failover.
_What the interviewer is probing for:_ Whether the candidate designs for the realistic failure modes of IPsec at scale (redundancy, dynamic routing integration, consistent cryptographic configuration) rather than treating a single static tunnel as sufficient for production connectivity.

## 12. Common Misconceptions

1. **"AH provides more security than ESP since it has 'Authentication' in the name."** ESP provides both encryption and authentication/integrity; AH provides only authentication/integrity with no encryption at all — ESP is the stronger and far more commonly used choice.
2. **"An 'established' IPsec tunnel means all expected traffic is flowing."** A tunnel can be fully established at the IKE level while specific subnets or traffic types fail to pass due to traffic-selector (Phase 2) gaps — "established" only confirms the control-plane negotiation succeeded, not that every expected data path works.
3. **"IPsec tunnels don't need dynamic routing since the tunnel itself defines what's reachable."** Static traffic selectors work for simple topologies, but production, multi-site, or multi-tunnel deployments commonly layer BGP over IPsec precisely so route changes and failover propagate automatically instead of requiring manual traffic-selector updates.
4. **"NAT and IPsec are fully compatible with no special handling needed."** NAT rewriting IP headers breaks AH's integrity check outright and complicates ESP as well, which is why NAT-T (encapsulating ESP inside UDP 4500) exists as a specific, necessary accommodation.

## 13. 🔑 Key Takeaways

- ESP (encryption + integrity) is the practical default over AH (integrity only, no encryption, and NAT-incompatible) for virtually all modern IPsec deployments.
- Tunnel mode wraps the entire original packet (including its header) inside a new outer packet, which is what enables gateway-to-gateway VPNs to carry private, non-routable addressing across the public internet.
- IKE's two-phase design (Phase 1: authenticate the gateways; Phase 2: negotiate the actual data-protection SAs) is the key mental model for diagnosing any IPsec tunnel failure — always determine which phase is failing first.
- NAT traversal (UDP 4500 encapsulation) is a necessary, common accommodation whenever an IPsec gateway sits behind a NAT device.
- Mismatched cryptographic proposals, traffic selectors, or SA lifetimes between the two tunnel endpoints — not exotic attacks — are the overwhelming majority of real-world IPsec operational issues.

## 14. Related Concepts & What's Next

This section's IPsec/IKE mechanics are the technical foundation for [§95](Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md), which covers how cloud providers expose IPsec as a managed site-to-site VPN gateway service, and for the BGP-over-VPN pattern referenced in this section's Architect answer, connecting back to [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) in Part 4. [§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md) immediately following contrasts this IPsec model against the alternative SSL/TLS VPN approach, and the NAT traversal discussion here connects back to the NAT/PAT fundamentals in [§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md).

**Next Section:** [§93](Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md) — `Section-93-Part11-SSL-TLS-VPNs-vs-IPsec-VPNs.md`
