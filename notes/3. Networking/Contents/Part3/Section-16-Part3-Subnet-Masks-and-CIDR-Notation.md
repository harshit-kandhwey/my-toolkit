# Section 16 (Part 3): Subnet Masks and CIDR Notation

## 1. Definition

**Plain language:** A subnet mask is a second 32-bit number that travels alongside an IP address and tells you which part of the address identifies the network and which part identifies the specific host on that network. CIDR notation is just a shorthand for writing that same mask as a slash followed by a count of bits — `/24` instead of `255.255.255.0` — and it's the notation used almost everywhere in modern networking and cloud tooling.

**Precise definition:** A **subnet mask** is a 32-bit value where a contiguous run of `1` bits (from the most significant bit) marks the **network portion** of an address and the remaining `0` bits mark the **host portion**. **CIDR (Classless Inter-Domain Routing)** notation, introduced by **RFC 1518/1519 in 1993**, expresses this same mask as a **prefix length** — the count of leading `1` bits — appended to an address with a slash, e.g., `192.168.1.0/24` means "the first 24 bits are network, the remaining 8 are host." CIDR replaced classful addressing by decoupling network/host boundaries from an address's class entirely, allowing **any** prefix length (0–32) on **any** address and enabling both subnetting (splitting a network into smaller ones) and **supernetting/route aggregation** (combining multiple networks into one advertised route, [§28](../Part4/Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md)).

> 💡 **Tip:** A subnet mask and a CIDR prefix length are two notations for the *exact same information* — never two different things. `/26` and `255.255.255.192` describe an identical 32-bit mask. Fluently converting between the two on sight (memorize the 9 possible non-zero final-octet values: `128, 192, 224, 240, 248, 252, 254, 255`, corresponding to `/25` through `/32`... and `0` for `/24`) removes an entire category of subnetting friction.

## 2. Why This Matters

- **CIDR is the universal language of modern networking configuration.** AWS VPC/subnet CIDR blocks, Azure VNet address spaces, GCP subnet ranges, Kubernetes pod/service CIDRs, `iptables`/security group rules — virtually every infrastructure tool expresses network ranges in CIDR, not dotted-decimal masks.
- **The AND operation between an IP and its mask is the single computation that determines "same network or different network."** Every routing decision, every "can host A reach host B without a router" judgment, boils down to this one bitwise operation.
- **Route aggregation (supernetting) is how the global internet routing table stays a manageable size.** Understanding CIDR as bit-boundary math (not classful boxes) is what makes aggregating `/24`s into a `/22` for an upstream route advertisement make sense.
- **Getting the prefix length wrong is one of the most common and costly IaC mistakes.** A `/16` VPC where a `/24` was intended (or vice versa) changes the address space by a factor of 256 — this either exhausts address planning or wastes an enormous block silently.
- **Certification and interview ubiquity.** CIDR arithmetic (finding network/broadcast addresses, host counts, whether two addresses share a subnet) is tested more than almost any other single networking skill across cloud and infrastructure interviews.

## 3. Prerequisites and Dependencies

Builds directly on [§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) — the binary octet structure and manual conversion skill developed there is the mechanism this section applies to masks specifically. This section is itself the prerequisite for [§17](Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md) (the actual subnetting workflow) and [§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md) (VLSM). Route aggregation built on CIDR is expanded in [§28](../Part4/Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md).

## 4. Architecture / Conceptual Diagram

```text
              192.168.1.10/26  — decomposed

  Address:   11000000.10101000.00000001.00 001010
  Mask:      11111111.11111111.11111111.11 000000    (/26 = 26 leading 1-bits)
             └──────────── network (26) ──┘└─host(6)─┘

  Bitwise AND (address & mask) → NETWORK ADDRESS:
             11000000.10101000.00000001.00 000000  =  192.168.1.0

  CIDR PREFIX ↔ SUBNET MASK ↔ HOST COUNT (last octet only, common cases)
  ┌────────┬───────────────────┬────────────────┬───────────────┐
  │ Prefix │ Mask (last octet) │ Hosts (2^n - 2)│  Total addrs  │
  ├────────┼───────────────────┼────────────────┼───────────────┤
  │  /24   │        .0         │      254        │      256      │
  │  /25   │       .128        │      126        │      128      │
  │  /26   │       .192        │       62        │       64      │
  │  /27   │       .224        │       30        │       32      │
  │  /28   │       .240        │       14        │       16      │
  │  /29   │       .248        │        6        │        8      │
  │  /30   │       .252        │        2        │        4      │
  │  /31   │       .254        │  0 (RFC 3021: 2 usable, point-to-point) │  2  │
  │  /32   │       .255        │  1 (host route) │       1       │
  └────────┴───────────────────┴────────────────┴───────────────┘
```

- The **AND operation** between address and mask is the entire mechanism: every bit position where the mask is `1`, keep the address bit; every position where the mask is `0`, force to `0`. The result is the **network address**.
- A valid subnet mask is always a contiguous run of `1`s followed by a contiguous run of `0`s — `11111111.11111111.00000000.11111111` (1s, then 0s, then 1s again) is not a legal subnet mask, even though nothing in raw binary prevents writing it.
- CIDR's power over classful masks: a `/26` can be applied to an address that used to be "Class C" (192.x) or "Class A" (10.x) identically — the prefix length is completely independent of the address's leading bits.
- **Route aggregation** works in the opposite direction from subnetting: instead of borrowing bits to make smaller networks, a router advertises a shorter prefix (e.g., `/22` instead of four separate `/24`s) when the underlying addresses are contiguous and share a common shorter prefix, shrinking routing table size.

## 5. Hands-On

### 5.1 Converting Between CIDR Prefix and Dotted-Decimal Mask by Hand

**Purpose:** Build fluency converting `/N` to its equivalent mask and back, the most frequent single operation in subnetting work.

**Syntax:** Write `N` ones followed by `(32-N)` zeros, then group into four 8-bit octets and convert each to decimal.

**Example usage and expected output:**

```text
/20  →  11111111.11111111.11110000.00000000
        └───8────┘└───8────┘└──4+4─┘└───8────┘
     =  255.255.240.0

Check: third octet has 4 leading 1s → 128+64+32+16 = 240 ✓
```

**Production usage example:** Reading a router's or cloud provider's exported configuration that shows a raw mask (`255.255.240.0`) instead of CIDR notation, and needing to mentally translate it back to `/20` to compare against design documentation written in CIDR.

**Common errors:** Miscounting bits when the prefix length doesn't land on an octet boundary (`/20`, `/26`, `/28`, etc.) — always explicitly write out the bit string first rather than trying to shortcut straight to the decimal value until the conversion is automatic.

### 5.2 Computing Network Address via Bitwise AND with `ipcalc`

**Purpose:** Verify the AND operation mechanically instead of trusting a mental shortcut, especially for addresses that don't fall on convenient boundaries.

**Syntax:**

```bash
ipcalc <address>/<prefix>
```

**Example usage and expected output:**

```bash
$ ipcalc 10.4.201.77/22
Address:   10.4.201.77           00001010.00000100.110010 01.01001101
Netmask:   255.255.252.0 = 22    11111111.11111111.111111 00.00000000
Wildcard:  0.0.3.255             00000000.00000000.000000 11.11111111
=>
Network:   10.4.200.0/22         00001010.00000100.110010 00.00000000
HostMin:   10.4.200.1
HostMax:   10.4.203.254
Broadcast: 10.4.203.255
Hosts/Net: 1022
```

**Production usage example:** Confirming, during subnet planning, exactly which `/22` an arbitrary-looking address like `10.4.201.77` belongs to before deciding whether a new host's address falls inside an already-allocated block or requires a new one.

**Common errors:** Assuming the network address is always "round" in the octet that contains the boundary — `10.4.200.0` is correct here, not `10.4.201.0`, because 200 is the correctly-masked boundary at /22 (multiples of 4 in the third octet: 200, 204, 208...), not multiples of 1.

### 5.3 Validating CIDR Blocks Programmatically Before They Reach a Cloud API

**Purpose:** Catch malformed or overlapping CIDR blocks in Infrastructure as Code before `terraform apply`/`aws ec2 create-subnet` rejects them, or worse, silently creates an unintended overlap.

**Syntax:**

```python
import ipaddress
net = ipaddress.ip_network("10.0.0.0/22", strict=True)
```

**Example usage and expected output:**

```bash
$ python3 -c "import ipaddress; print(ipaddress.ip_network('10.0.1.0/22', strict=True))"
Traceback (most recent call last):
    ...
ValueError: 10.0.1.0/22 has host bits set

$ python3 -c "import ipaddress; print(ipaddress.ip_network('10.0.0.0/22', strict=True))"
10.0.0.0/22
```

**Production usage example:** A pre-deployment validation step in an IaC pipeline (a CI script, or a Terraform `precondition` block, wrapping this same `strict=True` check) that rejects any subnet variable where parsing fails, catching the very common mistake of specifying a network address that actually has host bits set (like `10.0.1.0/22`, which should be `10.0.0.0/22`) before it ever reaches the cloud provider's API.

**Common errors:** Using `strict=False` (or omitting `strict` in older API versions where the default differed) silently masks off the host bits instead of raising an error — appropriate for defensively normalizing user input, but dangerous if the goal is to *catch* a caller's mistake rather than paper over it.

## 6. Production Usage Notes

- Nearly every cloud provider CIDR field (VPC CIDR, subnet CIDR, security group source/destination) is CIDR notation exclusively — dotted-decimal masks are essentially never used in modern cloud consoles, though they persist in on-prem router/firewall configuration and older network gear.
- Subnet size planning should work backward from **required host count plus growth headroom**, not forward from "whatever prefix looks standard" — a `/26` (62 usable hosts) chosen for a subnet that needs to grow to 100 hosts is a design mistake that forces disruptive re-IP work later.
- Cloud providers reserve additional addresses beyond the classic network/broadcast pair inside every subnet (AWS reserves 5 addresses per subnet: network, VPC router, DNS, future use, and broadcast) — always check the provider's specific reservation count when planning exact host capacity, since generic CIDR math slightly overstates usable addresses in a cloud VPC subnet specifically.

## 7. Security Considerations

- An overly broad CIDR in a security group or firewall rule (`0.0.0.0/0` where `10.0.0.0/8` was intended, or a `/16` where a `/28` was intended) is one of the most common causes of accidental over-exposure — CIDR literals in security-relevant configuration deserve the same review rigor as authentication code.
- CIDR-based ACLs are matched purely on the source/destination address bits — they say nothing about the *authenticity* of that address; an attacker capable of source-address spoofing (mitigated by BCP 38 ingress filtering) can attempt to match an allow-listed CIDR without actually being on that network.
- Route aggregation (supernetting) done incorrectly at a network boundary can accidentally advertise or leak routes for address space the organization doesn't actually control — a well-known class of real-world routing incident (accidental route leaks) traces back to imprecise CIDR aggregation.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                     | Resolution Path                                                                                                |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Cloud API rejects a subnet CIDR with "invalid CIDR block" or similar          | The specified address has host bits set (not the actual network address for that prefix length)     | Recompute network address via AND operation or `ipcalc`; use the corrected network address, not the raw intended host address |
| Two hosts on "the same subnet" per documentation can't reach each other directly | Mask mismatch — one host is configured with a different prefix length than the rest of the subnet, so it computes a different network address | Verify configured subnet mask/prefix length matches on all hosts on the segment, not just the IP address itself |
| Firewall rule matches far more traffic than intended                         | CIDR prefix length is shorter (broader) than intended — e.g., `/16` typed where `/24` was meant       | Recompute intended host count from requirements and correct the prefix length; add automated CIDR-width review to IaC PRs |

## 9. Best Practices

- Always express and document network ranges in CIDR notation (`/N`) as the primary form; convert to dotted-decimal mask only when a specific legacy tool or on-prem device requires it.
- Size every subnet's prefix length from actual (or reasonably projected) host count, not a "standard-looking" default — pair every CIDR in design documentation with an explicit usable-host-count comment.
- Validate CIDR literals programmatically in CI (Terraform `cidrhost`/`cidrsubnet` functions, or a `strict=True` parse in a pre-commit hook) rather than relying purely on human review of pull requests.

## 10. Common Anti-Patterns / Mistakes

- **Provisioning a network address with host bits still set.** Specifying `10.0.5.130/24` as a "network CIDR" when the network address is actually `10.0.5.0/24` — most cloud APIs reject this, but some on-prem tools silently normalize it, masking the underlying misunderstanding.
- **Choosing prefix lengths purely by habit ("/24 always") regardless of actual host count.** This either wastes address space at scale (hundreds of near-empty /24 subnets) or forces disruptive resizing later when a subnet's growth outpaces its fixed prefix.
- **Treating subnet mask and CIDR prefix as requiring separate mental models.** They are the same 32-bit value in two notations; maintaining two independent conversion tables instead of one unified mental model doubles the chance of an arithmetic slip.

## 11. Interview Questions

**🎯 Beginner:** _"What does the `/24` in `10.0.1.0/24` mean?"_
**Model answer:** It means the subnet mask has 24 leading `1` bits — the first 24 bits (the first three octets) identify the network, and the remaining 8 bits identify individual hosts within that network. It's equivalent to the dotted-decimal mask `255.255.255.0`, and gives 256 total addresses, 254 of which are usable for hosts (excluding the network and broadcast addresses).
_What the interviewer is probing for:_ Baseline comprehension that CIDR notation is a bit-count, not an arbitrary label.

**🎯 Intermediate:** _"Given the address `172.16.85.10/20`, calculate the network address, broadcast address, and usable host range. Show your work."_
**Model answer:** `/20` means 20 network bits, so within the third octet, 4 bits are network and 4 are host (since /16 covers the first two octets fully). The mask's third octet is `11110000` = 240. `85` in binary is `01010101`; masked with `11110000` gives `01010000` = 80. So the network address is `172.16.80.0`. The block spans 16 addresses in the third octet (80 through 95), so the broadcast address is `172.16.95.255`. Usable host range is `172.16.80.1` through `172.16.95.254`.
_What the interviewer is probing for:_ Real mechanical CIDR arithmetic under a non-octet-aligned boundary — the classic test of whether the candidate can actually do subnet math versus recite definitions.

**🎯 Senior:** _"Two adjacent teams each have a /24. Under what conditions can you replace both routes with a single aggregate route, and what could go wrong if you do it carelessly?"_
**Model answer:** Aggregation (supernetting) requires the two /24s to be contiguous and aligned on a boundary matching the shorter prefix — e.g., `10.0.2.0/24` and `10.0.3.0/24` can aggregate cleanly to `10.0.2.0/23` because 2 is even (properly aligned) and they're contiguous; `10.0.3.0/24` and `10.0.4.0/24` cannot aggregate to a single /23 because they don't share a common 23-bit prefix. Done carelessly — aggregating non-contiguous or misaligned blocks, or aggregating address space the organization doesn't fully control — the router ends up advertising reachability for addresses that either don't exist under that route or belong to someone else, which is exactly the mechanism behind real-world route-leak incidents.
_What the interviewer is probing for:_ Understanding that aggregation is a bit-alignment constraint, not just "these numbers are close together," plus awareness of the operational risk of getting it wrong.

**🎯 Architect:** _"You're designing IP address space for a new AWS Landing Zone that will eventually host 40 VPCs across multiple regions and accounts. How do you approach CIDR allocation to avoid conflicts, and what's the cost of getting the initial prefix sizing wrong?"_
**Model answer:** I'd start from a large enough supernet (e.g., a /16 or even larger, depending on projected total scale) reserved centrally, then carve out non-overlapping, sequentially-aligned blocks per region and per account/VPC — e.g., each region gets a /19 slice, each VPC within a region gets a /22 or /23 depending on projected workload size — documented in a central IPAM (IP Address Management) system or tool (many organizations use AWS IPAM specifically) rather than an ad hoc spreadsheet, since manual tracking at 40+ VPCs across accounts reliably produces overlaps. I'd also deliberately leave headroom: allocate slightly larger blocks than currently needed per VPC, because resizing a VPC's CIDR after workloads and peering/Transit Gateway routes are established is disruptive and sometimes requires re-IP'ing running infrastructure. The cost of getting initial sizing wrong compounds badly at this scale — an under-sized VPC CIDR discovered only after hundreds of ENIs/subnets are provisioned inside it often can't be fixed without downtime, since AWS VPC CIDR blocks (beyond secondary CIDR additions) are largely immutable once resources depend on the existing layout.
_What the interviewer is probing for:_ Whether the candidate thinks about CIDR allocation as an organization-wide, long-lived design problem with real remediation cost, not just a per-VPC arithmetic exercise.

## 12. Common Misconceptions

1. **"A /25 and a /26 differ by a small, roughly similar amount of address space."** Each single bit of prefix length halves (or doubles) the address space — a /25 has 128 addresses, a /26 has 64; the difference compounds fast, not linearly, as prefix length changes.
2. **"CIDR notation and dotted-decimal masks are different technologies."** They are two notations for the identical 32-bit mask value; there is no functional difference, only a display convention difference.
3. **"A subnet mask can be any arbitrary 32-bit pattern."** A valid mask must be a contiguous run of 1s followed by a contiguous run of 0s — patterns like `255.0.255.0` are not legal subnet masks even though they're syntactically valid dotted-decimal.
4. **"Route aggregation always works whenever prefixes happen to be numerically close."** Aggregation requires the underlying blocks to be contiguous and bit-aligned to the shorter prefix — proximity in decimal doesn't guarantee that alignment.

## 13. 🔑 Key Takeaways

- A subnet mask and a CIDR prefix length (`/N`) encode the identical information — a count of leading network bits — in two different notations.
- The network address is computed by a bitwise AND of the IP address against its mask; every routing and "same subnet" decision reduces to this operation.
- CIDR (1993) decoupled prefix length from address class, enabling both subnetting (splitting networks) and supernetting/aggregation (combining routes) at any bit boundary.
- Subnet sizing should be driven by actual required host count plus growth headroom, not habit — each additional bit of prefix length halves available addresses.
- Cloud provider APIs validate that submitted CIDRs are true network addresses (no host bits set); this is a frequent source of IaC validation errors worth catching before `apply`.

## 14. Related Concepts & What's Next

[§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) supplied the binary octet foundation this section applied to masks and prefixes specifically. [§17](Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md) takes CIDR notation and builds the full subnetting workflow — borrowing bits from the host portion to create multiple smaller networks. [§28](../Part4/Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md) revisits the aggregation/supernetting direction introduced briefly here in the context of routing protocol design.

**Next Section:** [§17](Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md) — `Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md`
