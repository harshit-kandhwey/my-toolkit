# Section 17 (Part 3): Subnetting Fundamentals: Borrowing Bits, Calculating Ranges

## 1. Definition

**Plain language:** Subnetting is the process of taking one larger network and splitting it into multiple smaller networks by "borrowing" bits from the host portion of the address and giving them to the network portion. Instead of one big flat network of, say, 254 hosts, you can carve that same space into four separate 62-host networks — each isolated from the others at Layer 3, each with its own network and broadcast address.

**Precise definition:** **Subnetting** is the process of extending a network's prefix length (moving the mask boundary further right, into what was host-portion bits) to divide one address block into `2^n` equally-sized smaller blocks, where `n` is the number of bits borrowed. Each resulting subnet has its own **network address** (all host bits `0`), **broadcast address** (all host bits `1`), and a **usable host range** (everything between them). The number of usable hosts per subnet is `2^h - 2`, where `h` is the number of remaining host bits (the `-2` accounts for the reserved network and broadcast addresses — this changes in specific cloud-provider contexts, see [§6](../Part1/Section-06-Part1-Bandwidth-Throughput-Latency-and-Jitter-Core-Vocabulary.md)). Subnetting trades host capacity per subnet for a larger number of smaller, more isolated broadcast domains and routing boundaries.

> 💡 **Tip:** Every subnetting problem reduces to answering three questions in order: (1) how many bits do I need to borrow to get enough subnets? (2) what's the new prefix length and block size? (3) what are the network/broadcast/usable-range boundaries for each resulting block? Work through these three questions explicitly, every time, rather than pattern-matching to memorized answers — it's the only approach that generalizes to problems that don't look like a textbook example.

## 2. Why This Matters

- **Subnetting is the mechanism behind nearly every real network segmentation decision.** Separating a "web tier" subnet from a "database tier" subnet, isolating a management network, or splitting address space across availability zones are all applications of borrowing bits to create smaller blocks.
- **Broadcast domain size has real performance and security implications.** A flat, unsubnetted /16 network puts tens of thousands of hosts in one broadcast domain — ARP traffic and broadcast storms scale with domain size; subnetting bounds that blast radius.
- **Getting subnet math wrong in production has immediate, visible consequences.** A miscalculated broadcast address or a subnet sized too small for its host count are not abstract mistakes — they show up as unreachable hosts or exhausted address pools during an incident.
- **Nearly every infrastructure and networking certification (CCNA, cloud associate-level exams, this repo's own AWS/Azure/GCP tracks) tests subnetting arithmetic directly**, because it's a mechanical skill that's unambiguous to verify.
- **Cloud VPC/subnet design is subnetting with a different vocabulary.** An AWS VPC `/16` split into per-AZ `/20` subnets is the exact same borrowing-bits operation covered here, just performed once at VPC design time instead of on physical switches.

## 3. Prerequisites and Dependencies

Requires [§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) (binary octet fluency) and [§16](Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md) (CIDR/mask equivalence and the AND operation) directly — this section is the practical application of both. [§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md) extends this section's fixed-size subnetting into variable-length subnetting for unequal-sized requirements.

## 4. Architecture / Conceptual Diagram

```text
        Starting block: 192.168.10.0/24  (256 addresses, 254 usable)
        Requirement: 4 equally-sized subnets  →  borrow 2 bits (2^2 = 4)

        Original:  /24  11111111.11111111.11111111.00000000
        New mask:  /26  11111111.11111111.11111111.11000000
                                                     └┬┘└──┘
                                              borrowed(2)  host(6)

        Resulting subnets (each /26, 64 addresses, 62 usable):

        ┌──────────────────┬────────────────┬────────────────┬──────────────────┐
        │   Subnet 0        │   Subnet 1      │   Subnet 2      │   Subnet 3        │
        │ 192.168.10.0/26   │ 192.168.10.64/26│192.168.10.128/26│192.168.10.192/26  │
        │ Net:  .0          │ Net:  .64       │ Net:  .128      │ Net:  .192        │
        │ Host: .1–.62      │ Host: .65–.126  │ Host: .129–.190 │ Host: .193–.254   │
        │ Bcast:.63         │ Bcast:.127      │ Bcast:.191      │ Bcast:.255        │
        └──────────────────┴────────────────┴────────────────┴──────────────────┘

        The increment between subnets = block size = 2^(host bits) = 2^6 = 64
```

- **Borrowing `n` bits** always produces exactly `2^n` equally-sized subnets, each with `2^(original host bits - n)` total addresses.
- The **increment** (the jump between one subnet's network address and the next) equals the block size — once you know a /26 block is 64 addresses wide, you know every subnet boundary is a multiple of 64 in the affected octet, with zero additional calculation needed.
- The **first** and **last** subnets in a subnetted range are just as valid and usable as the middle ones on modern networks — the old convention of avoiding the "subnet zero" and "all-ones subnet" (from ambiguity in very old, pre-RFC 1878 equipment) is obsolete; virtually all modern routers, cloud platforms, and the current RFCs treat them as fully usable.
- Every individual subnet still separately reserves its own network and broadcast address — subnetting a /24 into four /26s does not "recover" the four network/broadcast addresses that the original /24 reserved; it creates four new such pairs, one per subnet.

## 5. Hands-On

### 5.1 Determining Required Borrowed Bits from a Subnet Count Requirement

**Purpose:** Translate "I need N subnets" into "I need to borrow this many bits."

**Syntax:** Find the smallest `n` such that `2^n >= N`.

**Example usage and expected output:**

```text
Requirement: at least 5 subnets
2^2 = 4   (not enough)
2^3 = 8   (enough — borrow 3 bits)

Starting from /24, borrowing 3 bits → new prefix /27
Result: 8 subnets of /27 (32 addresses, 30 usable hosts each) —
        even though only 5 were required, the other 3 exist as spare capacity
```

**Production usage example:** Capacity planning for a multi-AZ VPC subnet layout, where the number of required subnets (one per AZ, per tier) determines the minimum borrowed bits, and remaining unused subnets are deliberately reserved for future AZ or tier expansion.

**Common errors:** Forgetting that unequal future growth (needing more subnets later than currently planned) argues for borrowing one extra bit up front, since re-subnetting an already-deployed and populated network later is disruptive.

### 5.2 Determining Required Borrowed Bits from a Host-Count Requirement (Reverse Direction)

**Purpose:** Translate "I need each subnet to support N hosts" into the maximum number of bits you're allowed to borrow.

**Syntax:** Find the smallest `h` (remaining host bits) such that `2^h - 2 >= N`; borrowed bits = original host bits − `h`.

**Example usage and expected output:**

```text
Requirement: each subnet must support at least 100 hosts
2^6 - 2 = 62   (not enough)
2^7 - 2 = 126  (enough — need 7 host bits remaining)

Starting from /24 (8 host bits), need 7 remaining → borrow only 1 bit
Result: /25 subnets, 2 subnets of 126 usable hosts each
```

**Production usage example:** Sizing a Kubernetes-adjacent worker-node subnet where each node consumes multiple IPs (node IP, pod IPs depending on CNI), so the "N hosts" figure must include per-node IP multiplication, not just node count, before running this calculation.

**Common errors:** Using total addresses (`2^h`) instead of usable hosts (`2^h - 2`) when comparing against a stated host requirement — this silently under-provisions by exactly 2 addresses per subnet, which matters at small subnet sizes.

### 5.3 Full Worked Problem: Subnetting a /22 Into Six Subnets of Varying Traffic Needs (Equal-Size Baseline)

**Purpose:** Walk a complete subnetting problem end-to-end using equal-sized subnets, as the baseline VLSM ([§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md)) will later show how to improve on.

**Syntax:** Given `10.8.0.0/22`, produce 6 equal subnets.

**Example usage and expected output:**

```text
Requirement: 6 subnets, need 2^n >= 6 → n=3 (2^3=8, closest power of 2 ≥ 6)
Original /22 has 10 host bits (32-22); borrow 3 → new prefix /25
Block size = 2^(10-3) = 2^7 = 128 addresses per subnet

10.8.0.0/22 spans 10.8.0.0 – 10.8.3.255 (1024 addresses total)

Subnet 0: 10.8.0.0/25    (10.8.0.1   – 10.8.0.126,   bcast 10.8.0.127)
Subnet 1: 10.8.0.128/25  (10.8.0.129 – 10.8.0.254,   bcast 10.8.0.255)
Subnet 2: 10.8.1.0/25    (10.8.1.1   – 10.8.1.126,   bcast 10.8.1.127)
Subnet 3: 10.8.1.128/25  (10.8.1.129 – 10.8.1.254,   bcast 10.8.1.255)
Subnet 4: 10.8.2.0/25    (10.8.2.1   – 10.8.2.126,   bcast 10.8.2.127)
Subnet 5: 10.8.2.128/25  (10.8.2.129 – 10.8.2.254,   bcast 10.8.2.255)
(Subnets 6-7 at 10.8.3.0/25 and 10.8.3.128/25 exist as unused spare capacity)
```

**Production usage example:** This is exactly the kind of table produced during an IP address management (IPAM) planning exercise for a new data center pod or VPC — documented once, referenced by every subsequent provisioning action.

**Common errors:** Forgetting that borrowing 3 bits from a /22 crosses into the third octet's bit boundary (not a clean octet-aligned split), so the block boundaries (`.0`, `.128`) alternate between the third and fourth octets — a frequent source of off-by-one mistakes if the arithmetic isn't written out fully.

### 5.4 Verifying Subnet Boundaries with `sipcalc` (Multi-Subnet Split Output)

**Purpose:** Cross-check a hand-computed subnetting scheme using a tool built specifically for split calculations.

**Syntax:**

```bash
sipcalc -s <n-subnets> <address>/<prefix>
```

**Example usage and expected output:**

```bash
$ sipcalc -s 4 192.168.10.0/24
-[ipv4 : 192.168.10.0/24] - 0

[Split network]
Network                 - 192.168.10.0/26 - 192.168.10.63
Network                 - 192.168.10.64/26 - 192.168.10.127
Network                 - 192.168.10.128/26 - 192.168.10.191
Network                 - 192.168.10.192/26 - 192.168.10.255
```

**Production usage example:** Generating a quick reference table during a design review meeting to confirm a proposed subnetting scheme matches what stakeholders expect, without opening a spreadsheet or writing a script.

**Common errors:** `sipcalc` is not installed by default on most systems (`apt install sipcalc`); confusing its `-s` (split into N subnets) flag with manually specifying a target prefix length produces a differently-structured (but not wrong) output that needs to be read carefully.

## 6. Production Usage Notes

- Cloud providers reserve more than the traditional 2 addresses (network + broadcast) per subnet. AWS reserves 5 addresses in every VPC subnet (network address, VPC router, DNS server, future use, and broadcast address) — so a `/26` (64 total addresses) yields 59 usable host addresses in an AWS subnet, not the textbook 62. Always confirm the provider's specific reservation before finalizing capacity math.
- Subnetting decisions made early in a network's life are expensive to undo later — hosts, DNS records, firewall rules, and routing tables all encode the original subnet boundaries; over-provision host bits modestly (one extra bit of host space) for subnets expected to grow, rather than sizing exactly to current known requirements.
- Documenting subnet plans as an explicit table (subnet name, CIDR, network/broadcast/usable range, purpose) rather than only as raw CIDR literals in code prevents the "what was this /27 originally for" question that arises during later incident response or audits.

## 7. Security Considerations

- Subnetting creates natural boundaries for applying differentiated security controls (firewall rules, security groups, NACLs) per tier or trust zone — a database subnet and a public web subnet should virtually always be separate subnets specifically so that Layer 3/4 controls can be applied at the subnet boundary rather than relying solely on host-level firewalling.
- Smaller broadcast domains (a consequence of subnetting) also limit the blast radius of Layer 2 attacks (ARP spoofing, broadcast storms) — this is a genuine, if secondary, security benefit of subnetting beyond pure address management.
- A subnet sized larger than its actual host count needs (over-provisioned host bits) unnecessarily broadens what a compromised host on that subnet can directly ARP-scan and reach at Layer 2 — right-sizing subnets is a mild but real defense-in-depth consideration, not purely an address-conservation one.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                   | Resolution Path                                                                                                     |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Host configured with an address that seems "in range" can't communicate with others on the subnet | The address is actually the network or broadcast address for that prefix length, not a usable host address | Recompute network/broadcast boundaries explicitly for the exact prefix in use; reassign the host to a genuinely usable address |
| A subnet runs out of usable addresses faster than expected               | Actual host-per-subnet requirement was under-estimated, or provider-specific reserved addresses weren't accounted for | Recompute required host bits with provider reservations included ([§6](../Part1/Section-06-Part1-Bandwidth-Throughput-Latency-and-Jitter-Core-Vocabulary.md)); resize or add an additional subnet |
| Two subnets that should be adjacent/non-overlapping show address conflicts | Off-by-one error in manual boundary calculation, often from an octet-crossing borrow (e.g., /22 → /25) | Recompute using the "increment = block size" rule and verify each boundary is a clean multiple of the block size |

## 9. Best Practices

- Always compute and record all three values for every subnet — network address, broadcast address, and usable range — never just the CIDR block, so ambiguity about "is .0 usable here" never has to be re-derived under time pressure.
- Reserve headroom by borrowing one fewer bit than the current exact requirement demands, when growth is plausible, rather than optimizing purely for current minimum address consumption.
- Cross-check every hand-calculated subnet scheme with a tool (`sipcalc`, `ipcalc`, or a script using `ipaddress`/`netaddr`) before committing it to design documentation or IaC — manual arithmetic errors are common even among experienced engineers.

## 10. Common Anti-Patterns / Mistakes

- **Sizing every subnet identically regardless of actual per-subnet host requirements.** A management subnet needing 5 hosts and a web-tier subnet needing 200 hosts forced into the same fixed prefix length either wastes enormous address space on the small subnet or under-provisions the large one — this is precisely the problem VLSM ([§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md)) solves.
- **Forgetting cloud-provider-specific address reservations when calculating usable host capacity.** Assuming textbook `2^h - 2` math applies unmodified inside an AWS/Azure/GCP subnet leads to under-provisioned capacity planning by several addresses per subnet.
- **Avoiding the first or last subnet in a subnetted range out of outdated habit.** The old "never use subnet zero or the all-ones subnet" convention is obsolete on virtually all modern equipment and cloud platforms; needlessly avoiding them wastes usable address space for no current benefit.

## 11. Interview Questions

**🎯 Beginner:** _"If you borrow 2 bits from a /24 network, how many subnets do you get, and what's the new prefix length?"_
**Model answer:** Borrowing `n` bits always produces `2^n` subnets, so borrowing 2 bits produces `2^2 = 4` subnets. The new prefix length is the original prefix plus the borrowed bits: /24 + 2 = /26.
_What the interviewer is probing for:_ Basic grasp of the bits-borrowed-to-subnet-count relationship, the single most fundamental subnetting formula.

**🎯 Intermediate:** _"You have `172.20.0.0/20` and need at least 10 equally-sized subnets. What prefix length do you use, how many usable hosts does each subnet have, and what are the first two subnets' network addresses?"_
**Model answer:** Need `2^n >= 10`, so n=4 (`2^4=16` subnets, the smallest power of two at least 10). Original /20 has 12 host bits (32-20); borrowing 4 leaves 8 host bits, so new prefix is /24, giving `2^8 - 2 = 254` usable hosts per subnet. Block size (increment) is `2^8 = 256`, applied in the third octet since /20 to /24 crosses that boundary. First subnet: `172.20.0.0/24`. Second subnet: `172.20.1.0/24` (third octet increments by 1, since the increment here happens to equal exactly one full octet value).
_What the interviewer is probing for:_ Full end-to-end mechanical subnetting competence, including correctly tracking which octet the borrowed bits land in.

**🎯 Senior:** _"A team subnetted a /24 into eight /27s and is now told two more subnets are needed, but all eight are already assigned to live environments. What are the real options, and what are the trade-offs?"_
**Model answer:** Borrowing all available bits already used up the /24's subnetting headroom at that prefix length (2^3=8 subnets from 3 borrowed bits is the maximum equal split at /27 from a /24). The real options: (1) find an entirely separate, unused address block and provision the new subnets there, accepting non-contiguity with the existing scheme — usually the pragmatic answer if a spare block exists; (2) re-subnet by borrowing an additional bit (moving to /28), which doubles the number of subnets but requires re-IP'ing every host on all eight existing subnets since their broadcast/network boundaries all shift — highly disruptive, rarely justified purely for two more subnets; (3) if this address space sits inside a larger reserved supernet that was never fully allocated, carve the new subnets from that headroom instead. The trade-off is almost always disruption cost vs. address-space cleanliness — in practice, option (1), accepting a non-contiguous allocation from spare space, wins unless the organization has a strict policy requiring contiguous, aggregatable blocks for routing efficiency.
_What the interviewer is probing for:_ Real operational judgment about the disruption cost of re-subnetting live infrastructure, not just the arithmetic of finding more subnets on paper.

**🎯 Architect:** _"Design the subnetting scheme for a `/16` VPC that must support 4 availability zones, each needing a public tier (≤ 200 hosts), a private application tier (≤ 500 hosts), and a database tier (≤ 50 hosts), with room to add a 5th AZ later. Walk through your allocation."_
**Model answer:** I'd first size each tier's prefix from its host requirement with headroom: public tier ≤200 hosts needs a /24 (254 usable, comfortably covers 200 with room to grow); application tier ≤500 hosts needs a /23 (510 usable); database tier ≤50 hosts needs a /26 (62 usable, with headroom over 50) — accounting also for provider-specific reserved addresses ([§6](../Part1/Section-06-Part1-Bandwidth-Throughput-Latency-and-Jitter-Core-Vocabulary.md)) at each size, all margins here comfortably absorb that. That's 3 differently-sized blocks per AZ, which is a VLSM problem rather than equal-sized subnetting ([§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md)) — I would NOT force all three tiers into equal-sized subnets, since that would either waste enormous space on the database tier or under-provision the application tier. Within the /16 (65,536 addresses), I'd reserve one clean, aligned /20 or /21 chunk per AZ (large enough to hold that AZ's /23+/24+/26 comfortably plus future growth) and allocate 5 such chunks up front — 4 for immediate AZs, 1 reserved and untouched for the future 5th AZ — rather than densely packing only 4 AZs' worth and hoping later expansion fits in leftover fragments. This keeps each AZ's address range contiguous and documented, keeps room for the known future AZ without re-IP'ing existing infrastructure, and leaves the remaining /16 headroom (beyond the 5 reserved AZ chunks) available for entirely new requirements not yet identified.
_What the interviewer is probing for:_ Ability to combine host-count-driven sizing, VLSM thinking, and forward-looking capacity reservation into one coherent design, rather than mechanically subnetting without a growth strategy.

## 12. Common Misconceptions

1. **"Subnetting always produces equally-useful subnets regardless of tier needs."** Equal-sized subnetting is a starting baseline; real designs almost always need different-sized subnets per tier, which is what VLSM ([§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md)) is for.
2. **"The first and last subnets in a subnetted range are unusable or should be avoided."** This was true on some very old equipment predating RFC 1878 (1995); virtually every modern router, switch, and cloud platform treats them as fully usable.
3. **"Usable host count is always `2^h`."** It's `2^h - 2` for the traditional network+broadcast reservation, and often fewer still in cloud provider subnets that reserve additional addresses.
4. **"Borrowing bits and losing hosts is purely a cost with no benefit."** Smaller subnets/broadcast domains have real operational and security benefits (reduced broadcast traffic, smaller Layer-2 attack blast radius, cleaner per-tier firewall boundaries) that offset the reduced host count per subnet.

## 13. 🔑 Key Takeaways

- Subnetting borrows `n` bits from the host portion to produce `2^n` equally-sized smaller networks, each with its own network, broadcast, and usable-host-range boundaries.
- The increment between subnet boundaries always equals the resulting block size (`2^(remaining host bits)`) — once known, every boundary is a simple multiple of that increment.
- Usable hosts per subnet is `2^h - 2` in the textbook case, but cloud providers reserve additional addresses (AWS reserves 5 per subnet) that must be accounted for in real capacity planning.
- The "avoid subnet zero / all-ones subnet" convention is obsolete on all modern equipment and platforms.
- Always verify hand-calculated subnetting schemes with a tool (`ipcalc`, `sipcalc`, or a scripted `ipaddress`/`netaddr` check) before committing them to design documents or IaC.

## 14. Related Concepts & What's Next

[§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md) extends the equal-sized subnetting covered here into VLSM, where different subnets in the same allocation carry different prefix lengths sized to their actual, unequal host requirements — directly addressing the limitation surfaced in this section's worked examples. [§28](../Part4/Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md) revisits these same block boundaries from the opposite direction (aggregating many small subnets back into fewer, larger advertised routes).

**Next Section:** [§18](Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md) — `Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md`
