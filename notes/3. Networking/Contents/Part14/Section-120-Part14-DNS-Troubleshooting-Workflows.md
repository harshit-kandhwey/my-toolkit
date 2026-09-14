# Section 120 (Part 14): DNS Troubleshooting Workflows

## 1. Definition

**Plain language:** "It's always DNS" is a running joke in infrastructure engineering precisely because DNS sits invisibly underneath almost every connection an application makes, and its failures produce symptoms — timeouts, connections to the wrong host, intermittent errors — that look like almost anything else. A DNS troubleshooting workflow is the specific, ordered set of questions and tools used to confirm or rule out DNS as the actual root cause quickly, rather than discovering it last after exhausting every other possibility.

**Precise definition:** A **DNS troubleshooting workflow** is a structured sequence of resolution-path checks — querying a name against the client's configured resolver, against the authoritative name servers directly, and by walking the delegation chain from the root — used to determine at which specific stage a name resolution failure or incorrect result originates: a stale local/resolver cache, a misconfigured or lagging authoritative record, a broken delegation (missing or incorrect NS records) at any level of the hierarchy, or a client-side resolver misconfiguration. This builds directly on the record types, resolution model, and caching behavior introduced in Part 6 ([§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)-[§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md)), applying them as a diagnostic sequence rather than a set of standalone facts.

> 💡 **Tip:** The single highest-value habit in DNS troubleshooting is querying an authoritative server **directly**, bypassing every cache in between (`dig @<authoritative-ns> name`) — this immediately tells you whether the *source of truth* is correct, which either clears the authoritative side entirely or proves the problem is upstream of every cache you might otherwise waste time flushing.

## 2. Prerequisites and Dependencies

This section depends heavily on [§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)-[§49](../Part6/Section-49-Part6-DNSSEC-Chain-of-Trust-and-Threat-Model.md) (DNS fundamentals, record types, recursive/iterative resolution, and caching/TTL behavior) and directly extends [§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md)'s introduction of `dig`, `nslookup`, and `host` from standalone tool usage into a full diagnostic workflow. It assumes the zone-file and delegation concepts from [§48](../Part6/Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md) and benefits from [§50](../Part6/Section-50-Part6-Split-Horizon-Split-View-DNS.md)'s split-horizon DNS discussion, since split-horizon setups are a recurring, specific cause of "works from one network, not another" DNS symptoms. It follows [§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md) in the escalation path from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md), representing the domain-specific workflow for the single most common category of "mystery" connectivity failure — most engineers reach for this section's techniques even before considering a packet capture, since DNS problems are both extremely common and unusually cheap to rule in or out.

## 3. Why This Matters

- **DNS failures masquerade as almost every other kind of failure** — a stale cached record pointing at a decommissioned IP looks identical to "the server is down," and a missing record looks identical to "the network is unreachable," making DNS one of the first, not last, things worth ruling out.
- **The resolution chain has multiple independent points of caching and failure** (client OS cache, local/recursive resolver cache, and the authoritative servers themselves), and a workflow that checks them in a deliberate order avoids the common trap of "fixing" a record but still seeing the old result because a cache in between hasn't expired yet.
- **Cloud environments add their own DNS layer** (VPC-internal DNS, service discovery, split-horizon patterns for internal vs. external names) on top of public DNS, and a workflow that doesn't account for this layer will misdiagnose purely internal resolution problems as if they were public DNS issues.
- **DNS propagation delay is one of the most frequently misunderstood concepts in production incidents** — understanding TTL-driven caching precisely (rather than treating DNS changes as "instant") prevents both premature panic during a planned change and wasted effort chasing a "bug" that is actually just an unexpired cache entry.
- **A correct DNS workflow directly shortens the "wrong problem chased" tax** that shows up constantly in on-call rotations — DNS-adjacent symptoms sent down an application-debugging path first, before DNS is ruled out, waste disproportionate incident time relative to how cheap DNS checks actually are.

## 4. Architecture / Conceptual Diagram

```text
   DNS RESOLUTION CHAIN — WHERE EACH WORKFLOW STEP LOOKS

   Client application
        │
        ▼
   OS-level stub resolver / cache        ◄── Step 1: check here first
        │                                     (getent hosts, systemd-resolve)
        ▼
   Configured recursive resolver          ◄── Step 2: query THIS directly
   (ISP resolver, 8.8.8.8, VPC DNS,           (dig @<resolver> name)
    corporate internal resolver)
        │
        ▼
   Root → TLD → Authoritative NS chain    ◄── Step 3: walk the chain
        │                                     (dig +trace name)
        ▼
   Authoritative name server              ◄── Step 4: query THIS directly,
   (source of truth for the zone)             bypassing every cache
                                               (dig @<authoritative-ns> name)

   A mismatch between step 2's answer and step 4's answer means:
   something between the client and the authoritative source is
   caching a stale or wrong answer — the fix is a cache/TTL problem,
   not a record problem.

   A wrong answer even at step 4 means: the authoritative record
   itself is wrong — the fix is at the zone/registrar level.
```

- Each step in the chain is capable of caching independently — a workflow that jumps straight to "the record is wrong" without first isolating *which* layer is serving the stale/wrong answer risks "fixing" a correct authoritative record while the actual problem (a cache) goes untouched.
- `dig +trace` deliberately re-walks the delegation chain from the root, ignoring the locally configured resolver entirely — this makes it the tool of choice for confirming delegation itself is correct, independent of any caching behavior anywhere else in the chain.
- Split-horizon DNS ([§50](../Part6/Section-50-Part6-Split-Horizon-Split-View-DNS.md)) means the "authoritative" answer can legitimately and correctly differ depending on which network the query originates from — a workflow applied without awareness of this can misinterpret a correct internal-vs-external difference as a bug.

## 5. Hands-On

### 5.1 Comparing the Local Resolver's Answer Against an Authoritative Server

**Purpose:** Determine whether a wrong or stale DNS answer originates from caching somewhere upstream, or is actually correct at the authoritative source.

**Syntax:**

```bash
dig <name>                       # uses the system's configured resolver
dig @<authoritative-ns> <name>   # bypasses caching, queries the source directly
```

**Example usage and expected output:**

```bash
$ dig api.example.com +short
203.0.113.10

$ dig @ns1.example.com api.example.com +short
203.0.113.99
```

- The two answers differ — the locally configured resolver is returning a stale, previously-cached IP (`203.0.113.10`), while the authoritative server (`ns1.example.com`) already has the updated record (`203.0.113.99`).

**Production usage example:** This exact comparison is the standard first move after any DNS record change that "doesn't seem to have taken effect" — it immediately distinguishes "the change hasn't propagated yet due to TTL caching" (expected, just needs to wait) from "the change itself was never actually applied at the authoritative source" (a real configuration error needing correction).

**Common errors:** Assuming a mismatch always means "DNS is broken" rather than checking the record's TTL first — if the TTL was, say, 3600 seconds and the change was made two minutes ago, a stale cached answer is completely expected behavior, not a fault; only a mismatch persisting well past the TTL's expiry window indicates an actual problem.

### 5.2 Walking the Full Delegation Chain

**Purpose:** Confirm that delegation (NS records at each level: root, TLD, and the zone itself) is configured correctly, independent of any caching layer.

**Syntax:**

```bash
dig +trace <name>
```

**Example usage and expected output:**

```bash
$ dig +trace api.example.com

; <<>> DiG 9.18.1 <<>> +trace api.example.com
.                       518400  IN      NS      a.root-servers.net.
com.                    172800  IN      NS      a.gtld-servers.net.
example.com.            172800  IN      NS      ns1.example.com.
example.com.            172800  IN      NS      ns2.example.com.
api.example.com.        300     IN      A       203.0.113.99
```

**Production usage example:** When a domain fails to resolve at all (not just returning a stale answer, but failing outright — `SERVFAIL` or `NXDOMAIN` from every resolver), `dig +trace` reveals exactly where the delegation chain breaks — a common real-world cause is an expired domain registration, a misconfigured NS record at the registrar, or a zone that was moved to new name servers without updating the parent delegation, all of which show up clearly as a chain that stops resolving cleanly at a specific level.

**Common errors:** Misreading a `dig +trace` that succeeds all the way to a correct final answer as proof there's no DNS problem at all — a fully correct trace only proves delegation and the authoritative answer are fine; it says nothing about whether an intermediate *caching* resolver somewhere in the client's actual path is serving something different, which is exactly what 5.1's direct comparison is for.

### 5.3 Diagnosing Split-Horizon and Cloud-Internal DNS Discrepancies

**Purpose:** Correctly distinguish an intentional split-horizon DNS difference from a genuine misconfiguration when internal and external resolution disagree.

**Syntax:**

```bash
dig <name>                        # from inside the private network
dig @8.8.8.8 <name>               # from outside, using a public resolver
```

**Example usage and expected output:**

```bash
# From inside the VPC:
$ dig internal-api.example.com +short
10.0.4.15

# From an external network, via a public resolver:
$ dig @8.8.8.8 internal-api.example.com
;; ANSWER SECTION: (empty — NXDOMAIN, or resolves to nothing reachable externally)
```

**Production usage example:** This exact test is used to confirm a split-horizon setup ([§50](../Part6/Section-50-Part6-Split-Horizon-Split-View-DNS.md)) is behaving as designed — an internal-only name correctly resolving to a private IP from inside the network and correctly failing (or resolving differently) from outside is the expected, intended behavior, not a bug; the workflow's job here is to confirm this is deliberate design rather than an accidental leak or accidental unreachability.

**Common errors:** Treating a difference between internal and external resolution as automatically a problem to "fix" — in a correctly designed split-horizon setup, this difference is the entire point, and "fixing" it by exposing internal records externally (or vice versa) can be an active security regression rather than a bug fix.

## 6. Production Usage Notes

- Client-side OS resolver caches (`systemd-resolved`, Windows DNS Client service, `nscd`) add a caching layer *below* the recursive resolver itself — a workflow that only checks the recursive resolver's answer without also checking (and, if needed, flushing) the OS-level cache can miss a stale answer sitting entirely on the client machine.
- Cloud-internal DNS (Route 53 Resolver, Azure DNS Private Zones, Cloud DNS private zones — introduced conceptually in [§107](../Part12/Section-107-Part12-Cloud-DNS-and-Service-Discovery-Patterns.md)) behaves like a private, internal authoritative layer with its own propagation and caching characteristics distinct from public DNS — troubleshooting internal service-discovery names requires applying this same workflow but pointed at the cloud-internal resolver, not a public one like `8.8.8.8`.
- Lowering a record's TTL well ahead of a planned migration (a common practice: dropping TTL to 60 seconds a day or more before a cutover, then raising it back afterward) is a standard technique specifically to make the propagation window in step 1 of this workflow short and predictable during the actual change.

## 7. Security Considerations

- DNS cache poisoning and spoofing attacks specifically target the caching layers this workflow inspects — an unexpected, incorrect answer that persists even from a direct authoritative query (rather than clearing once caches expire) can indicate the authoritative zone itself has been compromised or altered without authorization, which is a security incident, not a routine DNS bug.
- DNSSEC ([§49](../Part6/Section-49-Part6-DNSSEC-Chain-of-Trust-and-Threat-Model.md)) provides cryptographic validation of the chain this workflow walks manually with `dig +trace` — in a DNSSEC-validated environment, a resolver returning `SERVFAIL` for a name that resolves fine with `+trace`'s unsigned walk can indicate a validation failure (a broken signature chain) rather than a simple delegation problem, and should be diagnosed with DNSSEC-aware tooling (`dig +dnssec`) rather than assumed to be a standard propagation issue.
- Querying external, untrusted resolvers directly from production infrastructure during troubleshooting should be done deliberately and with awareness that doing so reveals what names/queries the organization cares about — treat DNS query patterns from production hosts as data worth protecting, not a neutral diagnostic action.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                | Resolution Path                                                                                                     |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Record updated but old IP still resolving for some users               | Stale cache at the client, recursive resolver, or both — TTL not yet expired  | Confirm authoritative record is correct (5.1); wait out the TTL, or lower TTL ahead of future changes                |
| Domain fails to resolve entirely (SERVFAIL/NXDOMAIN everywhere)        | Broken delegation — missing/incorrect NS records at the registrar or zone level | Walk the chain with `dig +trace` (5.2) to find exactly where delegation breaks                                      |
| Internal service name resolves differently inside vs. outside the VPC | Split-horizon DNS working as intended, or a genuine leak/misconfiguration      | Confirm intended design (5.3) before treating the difference as a bug; check cloud-internal DNS zone configuration   |
| Resolution works from one office/network but not another               | Different DNS resolver configurations, or a resolver-specific cache/outage    | Compare `dig` output using each network's actual configured resolver directly with `dig @<that-resolver>`           |
| DNSSEC-validating resolver returns SERVFAIL while `+trace` succeeds     | Broken or expired DNSSEC signature chain                                       | Check the zone's DNSSEC signing status and chain of trust ([§49](../Part6/Section-49-Part6-DNSSEC-Chain-of-Trust-and-Threat-Model.md)) with `dig +dnssec`                                  |

## 9. Best Practices

- Always query the authoritative server directly as an early step, not a last resort — it is the fastest way to separate "the source of truth is wrong" from "something is caching a stale answer."
- Lower TTLs proactively ahead of any planned DNS change that needs to take effect quickly, and raise them back afterward once the change has stabilized — this makes propagation delay predictable rather than an unknown variable during troubleshooting.
- Treat a difference between internal and external resolution as a design question first ("is this a split-horizon setup, and is this the intended behavior?") before treating it as a bug to fix.

## 10. Common Anti-Patterns / Mistakes

- **Flushing every cache in sight before confirming where the actual stale answer lives.** This can mask the real problem (an authoritative record that was never actually updated) behind a temporary fix, and wastes effort compared to the targeted comparison in 5.1.
- **Assuming DNS changes take effect instantly.** TTL-driven caching is a deliberate, expected part of the system — panicking or making further changes before a change's TTL window has even elapsed is a common and avoidable mistake.
- **Treating a correct `dig +trace` result as proof there's no DNS problem at all.** As shown in 5.2, a fully correct trace only rules out delegation and authoritative-record problems — it says nothing about caching behavior further down the actual client's resolution path.

## 11. Interview Questions

**🎯 Beginner:** _"A DNS record was updated an hour ago but some users still see the old IP. What's happening?"_
**Model answer:** This is most likely expected TTL-driven caching behavior rather than a bug — DNS resolvers and clients cache answers for the duration of the record's TTL, so users whose resolver cached the old answer before the update will keep seeing it until that cached entry expires. I'd check the record's configured TTL; if it's, say, one hour, seeing stale answers up to an hour after the change is completely normal, and the fix is simply to wait, or to have lowered the TTL proactively before making the change.
_What the interviewer is probing for:_ Basic understanding of TTL and caching as the expected, not exceptional, behavior.

**🎯 Intermediate:** _"How would you determine whether a DNS problem is caused by a caching issue versus the authoritative record itself being wrong?"_
**Model answer:** I'd query the authoritative name server directly with `dig @<authoritative-ns> <name>`, bypassing every resolver and cache in between. If that direct query already returns the wrong or stale answer, the problem is at the source — the zone's actual record configuration needs to be fixed. If the direct authoritative query returns the correct answer but the client (or its configured recursive resolver) still returns something different, the problem is caching somewhere between the client and the authoritative source, and the fix is either waiting out the TTL or flushing the specific cache involved rather than touching the zone configuration at all.
_What the interviewer is probing for:_ Practical, correct use of the direct-authoritative-query technique as the key diagnostic move.

**🎯 Senior:** _"A service works fine when accessed from inside your VPC but fails to resolve from an external partner's network. How would you troubleshoot this?"_
**Model answer:** I'd first determine whether this is intentional split-horizon design or an actual misconfiguration by checking whether the name is meant to be internal-only. If it is meant to be internal-only, the external failure is expected and the partner needs a different, public-facing endpoint — not a DNS fix at all. If the name is meant to resolve externally too, I'd compare resolution from inside the VPC against resolution using a public resolver from outside (`dig @8.8.8.8`) to see exactly what the external world actually gets back, then check whether the public zone has the correct record at all, versus only the private/internal zone having been updated — a common real cause is a change applied only to the cloud-provider's private DNS zone ([§107](../Part12/Section-107-Part12-Cloud-DNS-and-Service-Discovery-Patterns.md)) while the public zone was never touched.
_What the interviewer is probing for:_ Awareness of split-horizon DNS as a deliberate pattern and the discipline to check intent before assuming a bug.

**🎯 Architect:** _"How would you design DNS operations and change processes for an organization to minimize DNS-caused incidents at scale?"_
**Model answer:** I'd standardize a pre-change TTL-lowering step as a required part of any DNS change runbook — lowering TTLs a safe margin ahead of any planned cutover and only raising them back once the change is confirmed stable, making propagation windows predictable rather than a source of incident-time uncertainty. I'd invest in synthetic monitoring that periodically queries both the authoritative source and representative recursive resolvers for critical names, alerting proactively on drift between them rather than waiting for a user report. I'd also formalize the split-horizon design decisions themselves (which names are meant to be internal-only, which external, and why) as documented, reviewable configuration rather than tribal knowledge, so an engineer investigating an internal/external resolution difference can quickly check intent rather than reverse-engineering it during an incident. Finally, I'd ensure DNSSEC validation status and signing health ([§49](../Part6/Section-49-Part6-DNSSEC-Chain-of-Trust-and-Threat-Model.md)) are monitored explicitly, since a broken signature chain produces a very different failure signature (SERVFAIL specifically at validating resolvers) that a team unfamiliar with DNSSEC can easily misdiagnose as a generic propagation issue.
_What the interviewer is probing for:_ Organizational, process-level thinking about preventing DNS incidents proactively, not just diagnosing them reactively.

## 12. Common Misconceptions

1. **"DNS changes take effect immediately everywhere."** Propagation is governed by each cache's TTL along the resolution chain — a change is only guaranteed visible everywhere once every relevant cache's TTL has expired.
2. **"If `dig +trace` succeeds, DNS is definitely fine."** It only confirms delegation and the authoritative answer are correct — it says nothing about caching behavior at any resolver actually in the client's real resolution path.
3. **"A difference between internal and external DNS resolution is always a misconfiguration."** It is frequently the intended behavior of a deliberate split-horizon design — the workflow's job is to confirm intent before treating a difference as a bug.
4. **"Flushing the local cache is always the right first troubleshooting step."** It can mask an actual authoritative-record problem by temporarily hiding the symptom — querying the authoritative source directly first is a more reliable way to isolate where the actual problem lives.

## 13. 🔑 Key Takeaways

- Querying the authoritative name server directly, bypassing every cache, is the single highest-value move for isolating whether a DNS problem is a caching issue or an actual record misconfiguration.
- `dig +trace` walks the full delegation chain independent of any local caching, making it the right tool specifically for diagnosing broken delegation.
- A difference between internal and external resolution results should be checked against intended split-horizon design before being treated as a bug.
- Lowering TTLs proactively ahead of planned DNS changes makes propagation delay predictable and shortens the uncertainty window during incidents.

## 14. Related Concepts & What's Next

[§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)-[§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md) provide the full DNS fundamentals — record types, resolution model, caching, zone transfers, DNSSEC, split-horizon, and the base tool introductions — that this section's workflow directly builds on and operationalizes. [§107](../Part12/Section-107-Part12-Cloud-DNS-and-Service-Discovery-Patterns.md)'s cloud DNS and service discovery concepts extend this workflow into cloud-internal resolution specifically. [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md) continues the troubleshooting methodology into routing and path-level problems, a different but sometimes-related category of "why can't this specific destination be reached" investigation, since a DNS answer pointing to a technically-correct but unreachable IP is exactly the handoff point between a DNS problem and a routing problem.

**Next Section:** [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md) — `Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md`
