# Section 19 (Part 3): Private vs. Public IP Ranges; RFC 1918

## 1. Definition

**Plain language:** Some blocks of IP addresses are set aside for use inside private networks only — they're never assigned to any organization on the public internet, and every corporate network, home network, and cloud VPC reuses the same handful of ranges internally. Every other address is "public" — globally unique, routable across the internet, and assigned by a regional registry.

**Precise definition:** **RFC 1918** (1996, obsoleting RFC 1597) reserves three blocks of IPv4 address space for **private internets**: `10.0.0.0/8`, `172.16.0.0/12`, and `192.168.0.0/16`. These addresses are **not globally unique** and **must never be routed on the public internet** — every ISP and internet backbone router is expected to drop traffic sourced from or destined to these ranges at their boundary. Because private addresses can be freely reused by any organization without coordination, they solved the early-1990s fear of IPv4 exhaustion for private/internal use, at the cost of requiring **NAT** ([§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md)) for any private host to communicate with the public internet. **Public IP addresses**, by contrast, are globally unique, allocated hierarchically from IANA down through five **Regional Internet Registries** (RIRs: ARIN, RIPE NCC, APNIC, LACNIC, AFRINIC) to ISPs and organizations, and are directly routable across the internet without translation.

> 💡 **Tip:** The three RFC 1918 blocks map directly onto the old classful boundaries from [§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md): `10.0.0.0/8` is a Class A block, `172.16.0.0/12` sits inside Class B space, and `192.168.0.0/16` is a Class C block. That's not a coincidence — the RFC's authors deliberately carved one reservation from each class to give network designers a large, medium, and small private option.

## 2. Why This Matters

- **Virtually every internal network an infrastructure engineer will ever touch — corporate LANs, home networks, and cloud VPCs/VNets — uses RFC 1918 addressing.** Fluency with these three ranges is a baseline, daily-use skill, not a niche fact.
- **NAT exists specifically because of private addressing.** Understanding why `10.0.0.5` can't be reached directly from the internet — and must be translated at a boundary — is a direct prerequisite for understanding NAT/PAT, one of the most operationally important concepts in this Part.
- **Address planning conflicts are a real, recurring problem** when connecting two private networks (via VPN, Direct Connect, VPC peering, a company merger) that happen to have chosen overlapping RFC 1918 ranges — this is one of the most common real-world networking headaches infrastructure engineers encounter.
- **Public IP address exhaustion (IPv4) is a genuine, ongoing constraint** that shapes real costs (cloud providers now charge separately for public IPv4 addresses) and is the primary driver behind IPv6 adoption ([§21](Section-21-Part3-IPv6-Addressing-Structure-Notation-and-Address-Types.md)).
- **Security posture depends on correctly distinguishing private from public-facing resources** — accidentally exposing a resource that should only be reachable via private addressing is a very common, very damaging misconfiguration class.

## 3. Prerequisites and Dependencies

Builds on [§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) (classful ranges, since the three RFC 1918 blocks are drawn from Class A/B/C space) and [§16](Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md) (CIDR notation used to express all three blocks). This section is the direct prerequisite for [§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md), which explains the translation mechanism that makes private addressing usable for internet-bound traffic at all.

## 4. Architecture / Conceptual Diagram

```text
                    RFC 1918 PRIVATE ADDRESS SPACE

  ┌─────────────────────┬──────────┬─────────────────┬───────────────────┐
  │  Block               │  Prefix  │  Address Count  │  Historical Class │
  ├─────────────────────┼──────────┼─────────────────┼───────────────────┤
  │ 10.0.0.0 – 10.255.255.255       │  /8      │  16,777,216     │  A (single /8)     │
  │ 172.16.0.0 – 172.31.255.255     │  /12     │  1,048,576      │  B (16 × /16)       │
  │ 192.168.0.0 – 192.168.255.255   │  /16     │  65,536         │  C (256 × /24)      │
  └─────────────────────┴──────────┴─────────────────┴───────────────────┘

  Other special reserved ranges to distinguish from RFC 1918 private space:
  127.0.0.0/8        Loopback (never leaves the host at all)
  169.254.0.0/16     Link-local / APIPA (RFC 3927 — auto-assigned, no DHCP reached)
  100.64.0.0/10      Carrier-Grade NAT / Shared Address Space (RFC 6598)

           PRIVATE NETWORK                     PUBLIC INTERNET
    ┌───────────────────────┐
    │  10.0.1.10 (private)  │──┐
    │  10.0.1.11 (private)  │──┤       ┌─────────┐      ┌────────────┐
    │  10.0.1.12 (private)  │──┼──────►│   NAT   │─────►│  203.0.113.5│ (public,
    └───────────────────────┘  │       │ boundary │      │  globally  │
                                └──────►│ (§20)   │      │  unique)   │
                                        └─────────┘      └────────────┘
    Private addresses are reused independently in every organization's
    network; NAT at the boundary is what makes outbound reachability work.
```

- **RFC 1918 addresses are not globally unique by design** — the same `10.0.1.10` exists simultaneously inside thousands of unrelated organizations' networks, which is exactly why it cannot be routed on the public internet (a public router would have no way to know which of thousands of `10.0.1.10`s a packet was meant for).
- **Link-local addresses (`169.254.0.0/16`)** are a distinct reserved range from RFC 1918 — a host self-assigns one when DHCP fails, and it is not intended for any routed use at all, private or public; seeing one in production is almost always a symptom of a DHCP failure, not intentional addressing.
- **Carrier-Grade NAT space (`100.64.0.0/10`, RFC 6598)** exists specifically so ISPs performing large-scale NAT of their own don't collide with a customer's own RFC 1918 addressing behind a home router — a distinct, less commonly known reserved block worth recognizing.

## 5. Hands-On

### 5.1 Verifying Whether an Address Falls in RFC 1918 Space Programmatically

**Purpose:** Reliably classify an address as private or public without relying on memorized ranges alone, especially for the less-obvious boundaries (`172.16.0.0/12` is easy to get wrong by hand).

**Syntax:**

```python
import ipaddress
ipaddress.ip_address("172.20.5.1").is_private
```

**Example usage and expected output:**

```bash
$ python3 -c "import ipaddress; print(ipaddress.ip_address('172.20.5.1').is_private)"
True
$ python3 -c "import ipaddress; print(ipaddress.ip_address('172.32.5.1').is_private)"
False
```

**Production usage example:** Log-processing and SIEM pipelines routinely tag every source/destination IP with a private/public classification at ingest time (using exactly this kind of check) so that alerting rules can distinguish "internal-to-internal" traffic from traffic that touched the public internet.

**Common errors:** Manually eyeballing whether an address like `172.32.5.1` is inside `172.16.0.0/12` is a common mistake — the block only spans `172.16.0.0` through `172.31.255.255` (16 contiguous /16s), so `172.32.x.x` is actually public space, a boundary that's easy to misjudge without doing the bitwise check.

### 5.2 Identifying Whether the `172.16.0.0/12` Boundary Includes a Given Address, by Hand

**Purpose:** Understand exactly why the /12 boundary for the 172 block is not simply "172.16 through 172.31 by eyeballing the second octet."

**Syntax:** Convert the second octet to binary and check whether the first 4 bits match `0001` (16 through 31 in binary have `0001` as their high nibble).

**Example usage and expected output:**

```text
172.16.0.0/12 → second octet range check:
16  = 00010000   ✓ high nibble 0001
31  = 00011111   ✓ high nibble 0001
32  = 00100000   ✗ high nibble 0010 — outside the block

So 172.16.x.x through 172.31.x.x are private; 172.15.x.x and 172.32.x.x
onward are NOT part of RFC 1918 space, despite looking numerically close.
```

**Production usage example:** Writing a firewall rule or IAM condition intended to match "all RFC 1918 traffic" by hand (rather than a library call) requires getting this exact boundary right — a rule written as `172.0.0.0/8` to "cover the 172 private range" massively over-matches into public address space.

**Common errors:** Assuming the private range is `172.x.x.x` broadly, or manually writing `172.16.0.0/16` (missing 15 of the 16 actual /16 blocks in the true /12 range) are both common, consequential mistakes.

### 5.3 Detecting RFC 1918 Address Space Overlap Before a VPN or Peering Connection

**Purpose:** Catch overlapping private address ranges before connecting two networks — one of the most common real-world networking problems when merging environments.

**Syntax:**

```bash
ipcalc <network-A-cidr>
ipcalc <network-B-cidr>
# then compare ranges, or use a scripted overlap check
```

**Example usage and expected output:**

```bash
$ python3 - <<'EOF'
import ipaddress
a = ipaddress.ip_network("10.0.0.0/16")
b = ipaddress.ip_network("10.0.128.0/18")
print("Overlap:", a.overlaps(b))
EOF
Overlap: True
```

**Production usage example:** Before establishing a VPC peering connection, Transit Gateway attachment, or site-to-site VPN between two environments (particularly after an acquisition, where both companies independently chose `10.0.0.0/16` for their primary VPC), teams run exactly this kind of overlap check — a real overlap requires re-IP'ing one side or using NAT-based workarounds before the connection can function correctly, since overlapping private ranges cannot be routed between each other unambiguously.

**Common errors:** Only checking whether the top-level CIDR blocks look "different enough" by eye (`10.0.0.0/16` vs. `10.0.128.0/18`) without doing the actual overlap math — these two ranges do overlap despite looking distinct at a glance, since `10.0.128.0/18` falls entirely within `10.0.0.0/16`.

## 6. Production Usage Notes

- Cloud providers exclusively use RFC 1918 space (or a subset of it) as the default private address space for VPCs/VNets — AWS, Azure, and GCP all default to guiding new users toward `10.0.0.0/16`-style allocations, making overlap with on-prem or other cloud accounts using the same convention a very common real integration problem.
- Public IPv4 addresses are an increasingly billed, scarce resource in cloud environments — AWS, for instance, began charging per-hour for every public IPv4 address (including Elastic IPs) in 2024, a direct consequence of IPv4 exhaustion pressure; architecture decisions about how many resources genuinely need a public address (vs. sitting behind a NAT gateway or load balancer) now have a real, ongoing cost dimension.
- When designing multi-account or multi-VPC cloud environments expected to eventually interconnect (peering, Transit Gateway, on-prem VPN), agree on a non-overlapping RFC 1918 allocation scheme organization-wide *before* any VPCs are created — retrofitting non-overlapping addressing onto already-populated, interconnected environments is highly disruptive.

## 7. Security Considerations

- Private addressing is **not** a security boundary by itself — a host with a private IP behind NAT can still be directly reachable if a NAT/port-forwarding rule or a misconfigured security group exposes it; "it's on a private IP" is never a substitute for actual access controls.
- Public-facing resources accidentally assigned or exposed via a public IP when they were intended to remain private-only is one of the most common and most damaging cloud misconfiguration classes (an internet-facing database or admin panel that should have been private-subnet-only) — always audit which resources hold public IPs against which ones are actually supposed to be internet-reachable.
- RFC 1918 addresses appearing in inbound public internet traffic (as claimed source addresses) are a strong spoofing indicator, since legitimate RFC 1918 traffic should never egress onto the public internet unNAT'd — BCP 38/martian-address filtering at network boundaries should drop these on sight.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                        | Resolution Path                                                                                                     |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| VPN or VPC peering connection established, but hosts on one side can't reach hosts on the other | Both sides use overlapping RFC 1918 address ranges (common after independent design or a merger)      | Run an explicit overlap check (§5.3); re-IP one side, or introduce NAT at the connection boundary as a workaround   |
| A host has an address in `169.254.x.x` and can't reach anything             | DHCP failed and the host self-assigned a link-local (APIPA) address instead of getting a real lease   | Diagnose the DHCP failure ([§24](Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md)) rather than treating the 169.254 address itself as the problem |
| A firewall rule intended to match "internal RFC 1918 traffic broadly" also blocks legitimate public traffic, or misses some private traffic | Manually written CIDR list for RFC 1918 is incomplete or incorrectly bounded (e.g., `172.0.0.0/8` instead of `172.16.0.0/12`) | Recompute the exact three RFC 1918 CIDRs precisely ([§4](../Part1/Section-04-Part1-Network-Types-LAN-WAN-MAN-PAN-and-the-Data-Center-Network.md)) rather than approximating; use a library's `is_private` check where possible instead of hand-maintained lists |

## 9. Best Practices

- Standardize on a single, organization-wide RFC 1918 allocation scheme (which /8, /12, or /16-derived blocks belong to which region/account/environment) before any VPC or VLAN is created, specifically to avoid future overlap when environments need to interconnect.
- Use library functions (`ipaddress.is_private` in Python, equivalent in other languages) rather than hand-maintained CIDR lists when classifying addresses as private/public in code — the exact RFC 1918 boundaries (especially `172.16.0.0/12`) are easy to get subtly wrong by hand.
- Treat public IPv4 addresses as a cost- and security-relevant resource to be assigned deliberately (only to resources that genuinely need direct internet reachability), not a default.

## 10. Common Anti-Patterns / Mistakes

- **Assuming "private IP" implies "secure" or "unreachable from the internet."** Private addressing and actual network security controls (firewalls, security groups, NAT rules) are independent; a private address behind a misconfigured port-forward or exposed load balancer is fully reachable from the internet.
- **Hand-writing an approximate CIDR for the `172.16.0.0/12` block** (commonly `172.0.0.0/8` or `172.16.0.0/16`) instead of the precise range, either over- or under-matching in firewall rules and classification logic.
- **Choosing RFC 1918 ranges for new environments without checking against existing environments the new one might eventually need to connect to.** This is the single most common cause of the overlap problem described throughout this section, and it is entirely avoidable with minimal upfront coordination.

## 11. Interview Questions

**🎯 Beginner:** _"Name the three RFC 1918 private address ranges."_
**Model answer:** `10.0.0.0/8`, `172.16.0.0/12`, and `192.168.0.0/16`. These are reserved for private, internal networks and are never routed on the public internet.
_What the interviewer is probing for:_ Basic memorized fluency with the single most commonly referenced fact in this entire Part.

**🎯 Intermediate:** _"Is `172.32.15.4` a private, RFC 1918 address? Justify your answer with the actual boundary, not just intuition."_
**Model answer:** No. The RFC 1918 block in the 172 range is `172.16.0.0/12`, which covers only `172.16.0.0` through `172.31.255.255` — a /12 spans 16 contiguous /16 blocks (172.16 through 172.31 in the second octet). `172.32.x.x` falls just outside that boundary (the second octet's value 32 has a different high-order 4-bit pattern than 16-31), so it is a public address, even though it looks numerically close to the private range.
_What the interviewer is probing for:_ Whether the candidate actually understands the /12 boundary mechanically, rather than having memorized "172.16 to 172.31" as an opaque fact without knowing why it stops at 31.

**🎯 Senior:** _"Two companies are merging and both use `10.0.0.0/16` internally for their primary corporate VPCs. What are the real options for connecting the two networks, and what would you recommend?"_
**Model answer:** The core problem is a full address-space overlap — a direct VPC peering or VPN connection cannot route between two identical, fully-overlapping ranges since routing tables can't disambiguate which `10.0.5.10` a packet is destined for. Options: (1) re-IP one side's environment entirely onto a non-overlapping range — the cleanest long-term fix, but potentially highly disruptive depending on how much is hard-coded to the existing addressing; (2) use NAT (specifically a form of static or overlapping-network NAT, sometimes called "NAT66"-adjacent or double-NAT for IPv4) at the interconnection boundary to translate one side's range into a temporary non-overlapping range purely for the purposes of cross-network communication, without touching either side's internal addressing; (3) for a genuinely temporary or narrow-scope integration (only a few services need to talk cross-network), expose just those specific services via a proxy or gateway with its own non-overlapping address, avoiding full network-level integration entirely. I'd recommend starting with option 3 for anything time-sensitive post-merger, while planning option 1 (a real re-IP of the smaller or less-entrenched of the two environments) as the long-term fix, since NAT-based workarounds for full overlapping-network integration are operationally fragile and hard to reason about at scale.
_What the interviewer is probing for:_ Real-world judgment on a genuinely common, high-stakes scenario (merger-driven address overlap) rather than a purely textbook answer — the interviewer wants to see prioritization and trade-off reasoning, not just "use NAT."

**🎯 Architect:** _"Design an organization-wide IPv4 address allocation strategy for a company that expects to grow from 3 to 30+ AWS accounts across multiple regions over the next five years, all of which may eventually need to interconnect via Transit Gateway. How do you avoid the overlap problem described in the previous question, proactively?"_
**Model answer:** I'd reserve a single large RFC 1918 supernet centrally — most likely carved from `10.0.0.0/8`, since it offers by far the most address space (16.7 million addresses) of the three RFC 1918 blocks, giving the most headroom for 30+ accounts across multiple regions without needing to reuse `172.16.0.0/12` or `192.168.0.0/16` at all for VPCs (those smaller blocks can be reserved for other purposes, like point-to-point links or on-prem networks that need to stay clearly distinguishable from cloud VPC space). Within that supernet, I'd allocate non-overlapping, sequentially-numbered blocks per region first (e.g., each region gets a /12 or /14 slice), then per account within each region (each account gets a /16 or /20 depending on projected scale), tracked centrally in an IPAM system (AWS IPAM specifically, given the AWS context) rather than a spreadsheet, with the allocation policy documented and enforced at account-vending time (e.g., via AWS Control Tower or a custom account factory) so no team can self-select an arbitrary, potentially-overlapping CIDR when creating a new VPC. This makes every future account's addressing correct by construction rather than something that has to be manually checked for overlap after the fact, and specifically avoids the exact overlap crisis described in the merger scenario — because centrally-issued, sequentially-allocated blocks from one supernet are mathematically guaranteed not to overlap with each other as long as the allocation process itself is followed.
_What the interviewer is probing for:_ Ability to design proactive, governance-backed IP allocation at organizational scale — recognizing that the merger-overlap problem is best solved by never allowing it to occur in the first place, via centralized IPAM and account-vending policy, not by having a good remediation plan after the fact.

## 12. Common Misconceptions

1. **"Private IP addresses are inherently secure or hidden from attackers."** Private addressing only affects routability on the public internet; it provides zero security guarantee on its own — actual access control comes from firewalls, security groups, and NAT rules, which can still expose a private address.
2. **"The `172.16.0.0/12` private range covers all `172.x.x.x` addresses."** It covers only `172.16.0.0` through `172.31.255.255` — `172.0.x.x` through `172.15.x.x` and `172.32.x.x` onward are public address space.
3. **"Any organization can use any RFC 1918 range with zero coordination risk."** True in isolation, but the moment two independently-addressed private networks need to interconnect (VPN, peering, merger), overlapping choices become a real, disruptive problem — coordination matters as soon as connectivity is anticipated.
4. **"169.254.x.x (APIPA/link-local) is part of RFC 1918 private space."** It's a separate reservation (RFC 3927) for self-assigned addresses when DHCP fails, not part of the RFC 1918 private-network ranges, and its appearance is itself a diagnostic signal of a DHCP problem.

## 13. 🔑 Key Takeaways

- RFC 1918 reserves exactly three private address blocks — `10.0.0.0/8`, `172.16.0.0/12`, and `192.168.0.0/16` — none of which are globally unique or routable on the public internet.
- The `172.16.0.0/12` boundary is the one most commonly misjudged by hand; it covers only the second-octet range 16-31, not the full 172.x.x.x space.
- Private addressing provides zero security guarantee by itself — it is purely a routability/uniqueness distinction, not an access control.
- Overlapping RFC 1918 allocations between two networks that need to interconnect (VPN, peering, mergers) is one of the most common real-world networking problems, and is best prevented via centralized, coordinated allocation rather than remediated after the fact.
- Public IPv4 addresses are an increasingly scarce, billed resource in modern cloud environments, making deliberate (not default) public-address assignment a real architectural and cost consideration.

## 14. Related Concepts & What's Next

[§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md) explains the translation mechanism — NAT and PAT — that makes RFC 1918 private addresses usable for outbound internet communication at all, directly continuing from this section's private/public distinction. [§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) supplied the classful background explaining why the three RFC 1918 blocks are sized the way they are. [§21](Section-21-Part3-IPv6-Addressing-Structure-Notation-and-Address-Types.md) picks up the IPv4 exhaustion pressure referenced throughout this section as one of the central motivations for IPv6 adoption.

**Next Section:** [§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md) — `Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md`
