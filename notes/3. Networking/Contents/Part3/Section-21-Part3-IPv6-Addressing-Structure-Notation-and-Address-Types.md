# Section 21 (Part 3): IPv6 Addressing: Structure, Notation, and Address Types

## 1. Definition

**Plain language:** IPv6 is the successor to IPv4, using 128-bit addresses instead of 32-bit ones — a jump so large it's effectively impossible to exhaust the address space through normal use. It also writes addresses in hexadecimal groups separated by colons instead of decimal groups separated by dots, and introduces some genuinely new address types (like link-local, which every interface gets automatically) that don't have a clean IPv4 equivalent.

**Precise definition:** **IPv6**, standardized in **RFC 8200** (obsoleting the original RFC 2460), uses **128-bit addresses**, providing roughly **340 undecillion** (3.4 × 10^38) unique addresses — enough to assign a vast number of addresses to every person on Earth many times over, eliminating the address-scarcity pressure that drove NAT adoption ([§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md)) in IPv4. Addresses are written as **eight groups of four hexadecimal digits** separated by colons (e.g., `2001:0db8:85a3:0000:0000:8a2e:0370:7334`), with two standard compression rules: **leading zeros in each group may be omitted**, and **one contiguous run of all-zero groups may be replaced with a double colon (`::`)**, once per address. IPv6 defines several distinct **address types** by scope and purpose: **global unicast** (publicly routable, analogous to public IPv4), **link-local** (`fe80::/10`, automatically assigned to every interface, valid only on the local network segment), **unique local** (`fc00::/7`, RFC 4193's private-addressing analog to RFC 1918), **multicast** (`ff00::/8`, replacing IPv4 broadcast entirely — IPv6 has no broadcast address type), and **loopback** (`::1`, the single-address IPv6 equivalent of `127.0.0.1`).

> 💡 **Tip:** IPv6 did not simply "extend" IPv4's model with more bits — it removed broadcast as a concept entirely (replaced by multicast) and made link-local addressing mandatory and automatic on every interface, not optional. Approaching IPv6 as "IPv4 with longer addresses" causes real misunderstandings; treat the address-type model as genuinely redesigned, not just resized.

## 2. Why This Matters

- **IPv4 exhaustion is not hypothetical — it already happened.** IANA allocated the last IPv4 /8 blocks in 2011, and RIRs have been rationing or exhausted for years since; IPv6 is the actual, standards-track answer, not a speculative future technology.
- **Every major cloud provider now supports (and in some cases defaults to) IPv6 for new VPC/VNet deployments** — an infrastructure engineer who can't read or reason about IPv6 addressing is increasingly working with an incomplete picture of the network layer.
- **IPv6's elimination of broadcast and mandatory link-local addressing changes fundamental assumptions** infrastructure engineers carry over from IPv4 — NDP ([§23](Section-23-Part3-Address-Resolution-ARP-and-NDP.md)) replacing ARP is a direct consequence of this redesign, not a cosmetic renaming.
- **Address-space abundance changes design defaults.** NAT becomes largely unnecessary for address conservation under IPv6 (every device can have a globally unique address), shifting the conversation from "how do we conserve addresses" to "how do we still apply appropriate security boundaries without relying on NAT's incidental inbound-blocking behavior."
- **IPv6 literacy is directly tested in cloud certifications and increasingly assumed in senior infrastructure interviews**, as dual-stack ([§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md)) deployments become the norm rather than the exception.

## 3. Prerequisites and Dependencies

Builds conceptually on [§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) and [§16](Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md) (binary/CIDR fluency transfers directly, since IPv6 also uses CIDR-style prefix notation) and [§19](Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md) and [§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md) (the IPv4 exhaustion/NAT context this section's motivation directly responds to). This section is itself the prerequisite for [§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md) (IPv6 subnetting and dual-stack) and [§23](Section-23-Part3-Address-Resolution-ARP-and-NDP.md) (NDP, IPv6's address-resolution mechanism).

## 4. Architecture / Conceptual Diagram

```text
                  IPv6 ADDRESS STRUCTURE (128 bits, 8 groups of 16 bits)

  2001:0db8:85a3:0000:0000:8a2e:0370:7334
  └──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘└──┬─┘
    16b    16b    16b    16b    16b    16b    16b    16b   = 128 bits total

  Compression rules applied to the same address:
  2001:0db8:85a3:0000:0000:8a2e:0370:7334
  → 2001:db8:85a3:0:0:8a2e:370:7334        (drop leading zeros per group)
  → 2001:db8:85a3::8a2e:370:7334           (:: replaces ONE run of all-zero groups)

  ┌──────────────────────────┬────────────────┬───────────────────────────────┐
  │ Address Type              │  Range/Prefix  │  IPv4 rough analog             │
  ├──────────────────────────┼────────────────┼───────────────────────────────┤
  │ Global Unicast             │  2000::/3      │  Public IPv4                   │
  │ Link-Local                 │  fe80::/10     │  169.254.0.0/16 (APIPA) — but MANDATORY, not fallback │
  │ Unique Local (ULA)         │  fc00::/7      │  RFC 1918 private space         │
  │ Multicast                  │  ff00::/8      │  No IPv4 equivalent — replaces broadcast entirely │
  │ Loopback                   │  ::1/128       │  127.0.0.1                      │
  │ Unspecified                │  ::/128        │  0.0.0.0 (used only as source before an address is assigned) │
  └──────────────────────────┴────────────────┴───────────────────────────────┘
```

- **Link-local addresses are assigned automatically to every IPv6-enabled interface**, unconditionally — this is a structural difference from IPv4's link-local (169.254.x.x), which only appears as a DHCP-failure fallback. Every IPv6 interface has a link-local address whether or not it has any other address.
- **The `::` compression can only be used once per address** — using it twice would make the number of implied zero-groups ambiguous, so `2001::db8::1` is invalid notation.
- **There is no broadcast address type in IPv6.** Anything IPv4 used broadcast for (DHCP discovery, ARP) is replaced by specific multicast groups in IPv6 — the "all nodes" multicast address `ff02::1`, for instance, plays a broadcast-like role scoped specifically to the local link.
- **Unique Local Addresses (ULA, `fc00::/7`)** are IPv6's private-addressing analog to RFC 1918, but unlike RFC 1918's coordination-free reuse, ULA's `fd00::/8` sub-range expects a pseudo-random 40-bit global ID per organization specifically to make accidental collisions statistically unlikely even without central coordination — a deliberate improvement on RFC 1918's actual collision problem ([§19](Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md)).

## 5. Hands-On

### 5.1 Compressing and Expanding IPv6 Addresses by Hand

**Purpose:** Build fluency with the two compression rules, since misreading a compressed address is a common source of confusion.

**Syntax:** Apply leading-zero suppression per group, then collapse the single longest run of consecutive all-zero groups into `::`.

**Example usage and expected output:**

```text
Full:        fe80:0000:0000:0000:0202:b3ff:fe1e:8329
Step 1 (drop leading zeros per group):
             fe80:0:0:0:202:b3ff:fe1e:8329
Step 2 (collapse the run of three zero groups):
             fe80::202:b3ff:fe1e:8329

Expanding back: count total groups present (5: fe80, 202, b3ff, fe1e, 8329)
Need 8 total, so :: represents 8-5 = 3 zero groups → restores exactly to the full form.
```

**Production usage example:** Reading `ip -6 addr show` output or cloud console IPv6 address displays requires comfortably reading compressed notation at a glance — engineers who can't mentally expand `fe80::1` back to its full 8-group form will struggle to compare two addresses for equality or overlap by eye.

**Common errors:** Assuming `::` always represents exactly the same number of zero groups regardless of context — the number of implied groups depends entirely on how many explicit groups are present elsewhere in that specific address; it must be computed (8 minus the explicit group count), not memorized as a fixed value.

### 5.2 Inspecting IPv6 Addresses on a Live Interface

**Purpose:** Identify and distinguish link-local, ULA, and global unicast addresses assigned to a real interface.

**Syntax:**

```bash
ip -6 addr show
```

**Example usage and expected output:**

```bash
$ ip -6 addr show eth0
3: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qlen 1000
    inet6 2001:db8:85a3::1a2b/64 scope global
       valid_lft forever preferred_lft forever
    inet6 fe80::216:3eff:fe1e:8329/64 scope link
       valid_lft forever preferred_lft forever
```

**Production usage example:** During troubleshooting of dual-stack connectivity issues, confirming whether an interface actually has a global-scope IPv6 address (vs. only the mandatory link-local one) is often the first diagnostic step — a link-local-only interface cannot reach anything beyond its local segment.

**Common errors:** Mistaking the link-local address (`scope link`) for the interface's "real" address when troubleshooting external connectivity — link-local addresses are never valid for off-link communication and are the wrong thing to check when diagnosing internet reachability.

### 5.3 Validating and Comparing IPv6 Addresses Programmatically

**Purpose:** Reliably determine address type and equality without relying on manually expanding compressed notation.

**Syntax:**

```python
import ipaddress
addr = ipaddress.IPv6Address("fe80::1")
addr.is_link_local
```

**Example usage and expected output:**

```bash
$ python3 -c "
import ipaddress
a = ipaddress.IPv6Address('fe80::216:3eff:fe1e:8329')
print('link-local:', a.is_link_local)
print('global:', a.is_global)
b = ipaddress.IPv6Address('fe80:0000:0000:0000:0216:3eff:fe1e:8329')
print('equal to compressed form:', a == b)
"
link-local: True
global: False
equal to compressed form: True
```

**Production usage example:** Infrastructure automation that must classify or filter addresses by type (e.g., excluding link-local addresses from a DNS record or load balancer target list) relies on exactly this kind of library-based classification rather than string-matching on the compressed or expanded notation, which is unreliable given how many equivalent textual forms one address can have.

**Common errors:** Comparing two IPv6 addresses as raw strings instead of parsing them first — `fe80::1` and `fe80:0:0:0:0:0:0:1` are the identical address but will never match as strings, only as parsed address objects.

## 6. Production Usage Notes

- All major cloud providers now offer IPv6 support for VPCs/VNets and increasingly default new resources to dual-stack ([§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md)) — AWS, for instance, has begun charging for public IPv4 addresses specifically to push adoption toward IPv6 or private-only IPv4 where public reachability isn't required.
- Because IPv6 doesn't rely on NAT for address conservation, security posture in an IPv6-enabled environment shifts meaningfully toward firewall/security-group rules doing the actual access-control work that NAT's incidental inbound-blocking used to provide by accident in IPv4 — teams migrating to IPv6 sometimes discover gaps in explicit firewall policy that NAT had been masking.
- Link-local addresses require a **zone/scope identifier** when used outside routing tables in tooling (e.g., `ping6 fe80::1%eth0` on Linux, `ping fe80::1%12` referencing an interface index on Windows) because the same link-local address can legitimately exist simultaneously on multiple interfaces of the same host — a detail with no IPv4 equivalent that trips up engineers unfamiliar with it.

## 7. Security Considerations

- IPv6's vast address space makes brute-force address scanning of a subnet computationally infeasible (a /64 has 2^64 addresses) compared to IPv4's exhaustively scannable /24s — but this is not a substitute for actual access control, since a leaked or predictable address (many hosts derive part of their address from a MAC address, see EUI-64) can still be targeted directly.
- Because NAT's incidental inbound-blocking side effect ([§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md)) doesn't apply the same way when every host has a globally routable IPv6 address, firewalls and security groups must do the real, deliberate work of blocking unwanted inbound traffic — an environment that "worked safely" under IPv4 partly by accident of NAT can have real exposure gaps once IPv6 is enabled without equivalent, deliberate firewall rules.
- IPv6's mandatory link-local addressing and NDP ([§23](Section-23-Part3-Address-Resolution-ARP-and-NDP.md)) introduce their own local-segment attack surface (NDP spoofing, analogous to ARP spoofing in IPv4) that security tooling built purely around IPv4 assumptions may not account for.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                     | Resolution Path                                                                                                     |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| A host has an IPv6 address but can't reach anything beyond the local network | Only a link-local address is assigned (no global unicast address received via SLAAC/DHCPv6)        | Verify router advertisement / DHCPv6 configuration is providing a global-scope prefix; check `ip -6 addr show` for a `scope global` entry |
| A script comparing two IPv6 addresses reports them as different when they should be equal | Comparing raw, differently-compressed/expanded string representations instead of parsed address objects | Parse both addresses with a proper IPv6 library before comparing, never compare as raw strings                       |
| `ping6`/similar tooling to a link-local address fails with an ambiguous or "invalid argument" error | Missing the required zone/scope identifier (`%interface`) that link-local addresses need outside of routing context | Append the correct interface name or index as the zone identifier for the specific OS/tool in use                   |

## 9. Best Practices

- Always use a proper IPv6 library (`ipaddress` in Python, or the language/tool's equivalent) for any programmatic address parsing, comparison, or classification — never rely on string matching against compressed or expanded textual forms.
- Treat link-local addresses as strictly local-segment-only in tooling and documentation; never record them as a device's "real" or routable address in any inventory or DNS record.
- When enabling IPv6 in an existing IPv4-only environment, explicitly audit firewall/security-group policy for IPv6-equivalent rules rather than assuming existing IPv4 rules provide any protection — IPv4 and IPv6 traffic are filtered independently by virtually all firewall/security-group implementations.

## 10. Common Anti-Patterns / Mistakes

- **Treating IPv6 as "IPv4 with bigger numbers" and carrying over IPv4-specific assumptions unexamined** — particularly the assumption that NAT provides meaningful security, or that broadcast-based discovery mechanisms have a direct IPv6 equivalent (they're replaced by fundamentally different multicast/NDP mechanisms).
- **Comparing or deduplicating IPv6 addresses as raw strings** rather than parsing them, silently treating equivalent addresses as distinct due to differing compression in their textual representation.
- **Enabling dual-stack or IPv6-only networking without auditing security policy for IPv6-equivalent rules**, assuming existing IPv4 firewall rules provide coverage they structurally cannot.

## 11. Interview Questions

**🎯 Beginner:** _"How many bits does an IPv6 address have, and how is it typically written?"_
**Model answer:** 128 bits, more than four times the 32 bits of IPv4. It's written as eight groups of four hexadecimal digits separated by colons, e.g., `2001:0db8:85a3:0000:0000:8a2e:0370:7334`, with rules allowing leading zeros in each group to be dropped and one contiguous run of all-zero groups to be replaced with `::`.
_What the interviewer is probing for:_ Basic familiarity with IPv6's scale and notation as a starting point for deeper questions.

**🎯 Intermediate:** _"Compress the address `2001:0db8:0000:0000:0000:0000:0000:0001` fully, and explain both rules you applied."_
**Model answer:** First, drop leading zeros in each group: `2001:db8:0:0:0:0:0:1`. Second, collapse the single longest run of consecutive all-zero groups (here, five consecutive zero groups) into `::`: `2001:db8::1`. Both rules can be applied together but the `::` collapse can only be used once per address, since using it twice would make the number of implied zero groups ambiguous.
_What the interviewer is probing for:_ Actual mechanical fluency with both compression rules, and awareness of the "only once" constraint that trips up many candidates.

**🎯 Senior:** _"Explain why IPv6 doesn't have a broadcast address type, and what replaced the functionality IPv4 used broadcast for."_
**Model answer:** IPv6's designers deliberately removed broadcast because it forces every device on a segment to process every broadcast packet regardless of relevance, which doesn't scale well and was seen as an architectural mistake worth correcting in a clean-slate redesign. Multicast replaces it entirely: instead of "send to everyone and let them filter," IPv6 uses specific, well-known multicast groups that only interested devices join and listen to — e.g., `ff02::1` (all nodes on the local link) replaces the old broadcast-based "everyone listen" pattern, and `ff02::2` (all routers) lets only routers respond to router-specific queries. This same multicast-based redesign is also why address resolution moved from ARP (which relies on broadcast) to NDP (which uses multicast) — covered in [§23](Section-23-Part3-Address-Resolution-ARP-and-NDP.md).
_What the interviewer is probing for:_ Understanding that IPv6's removal of broadcast is a deliberate architectural choice with real downstream consequences (like NDP replacing ARP), not just a trivia fact about what IPv6 lacks.

**🎯 Architect:** _"Your organization is enabling IPv6 dual-stack across a previously IPv4-only production environment. What's the single most important security review you'd insist happen before rollout, and why?"_
**Model answer:** I'd insist on a full, independent audit of firewall and security-group rules specifically for IPv6 equivalence — confirming that every IPv4 rule currently providing meaningful access control (not just NAT's incidental inbound-blocking) has a deliberate, equally-restrictive IPv6 counterpart. The reason this is the single most important review: many environments have been "safe" partly by accident under IPv4, because NAT/PAT's stateful translation happened to block most unsolicited inbound connections even where explicit firewall policy was incomplete or overly permissive. The moment IPv6 is enabled, every dual-stack host typically receives a globally routable, directly reachable IPv6 address with no NAT layer in between by default — any host relying on that NAT side-effect for its actual security posture, rather than genuine firewall policy, becomes directly internet-reachable over IPv6 the instant dual-stack is turned on, even if its IPv4-side security posture looked fine. This is a well-documented, real-world class of incident in organizations that enabled IPv6 without an equivalent security review, and it's entirely preventable with a deliberate audit before rollout rather than after.
_What the interviewer is probing for:_ Recognition that IPv6's lack of reliance on NAT is a genuine, high-stakes security transition point, not just a technical footnote — and the ability to identify the specific, well-known real-world risk (NAT-masked firewall gaps) rather than a generic "do a security review" answer.

## 12. Common Misconceptions

1. **"IPv6 is just IPv4 with more bits, otherwise the same model."** IPv6 removed broadcast entirely (replaced by multicast), made link-local addressing mandatory rather than a fallback, and replaced ARP with NDP — these are genuine architectural redesigns, not cosmetic size increases.
2. **"`::` can be used as many times as needed in one address to save space."** It can only be used once per address, since multiple uses would make the number of implied zero groups ambiguous and the address unparseable.
3. **"IPv6 eliminates the need for any NAT-like concept entirely, forever."** While NAT for address conservation is largely unnecessary, related concepts (NAT64/NAT66) persist as transition mechanisms during dual-stack periods, and address-conservation NAT is different from any translation used for interoperability during migration.
4. **"A link-local address is just a fallback for when something goes wrong, like IPv4's APIPA."** Every IPv6-capable interface has a link-local address unconditionally and automatically, always, regardless of whether any other address is also assigned — it's a mandatory structural feature, not an error-condition fallback.

## 13. 🔑 Key Takeaways

- IPv6 uses 128-bit addresses (vs. IPv4's 32-bit), written as eight hex groups with two standard compression rules (leading-zero suppression, single-use `::` for consecutive zero groups).
- IPv6 defines distinct address types by scope — global unicast, link-local (mandatory on every interface), unique local (RFC 4193's RFC-1918 analog), multicast (replacing broadcast entirely), and loopback.
- There is no broadcast address type in IPv6; anything IPv4 used broadcast for is handled by specific multicast groups instead.
- IPv6's enormous address space removes the address-scarcity motivation for NAT, which shifts real security responsibility onto explicit firewall/security-group policy rather than relying on NAT's incidental inbound-blocking side effect.
- Always use a proper library for programmatic IPv6 address handling — the same address can have many valid, non-identical-looking textual representations.

## 14. Related Concepts & What's Next

[§19](Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md) and [§20](Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md) established the IPv4 address-scarcity and NAT context this section's motivation directly responds to. [§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md) applies the address structure covered here to actual subnetting practice and to running IPv4 and IPv6 side by side during a transition period. [§23](Section-23-Part3-Address-Resolution-ARP-and-NDP.md) covers NDP, the IPv6 address-resolution mechanism whose existence was foreshadowed here as a direct consequence of removing broadcast.

**Next Section:** [§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md) — `Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md`
