# Section 47 (Part 6): DNS Caching, TTLs, and Negative Caching

## 1. Definition

**Plain language:** Doing the full iterative walk from [§46](Section-46-Part6-Recursive-vs-Iterative-Resolution-Resolvers-and-Root-TLD-Authoritative-Servers.md) for every single DNS query would be wasteful and slow, so resolvers remember answers for a while instead of asking again immediately. How long they remember — and what they remember when the answer is "this name doesn't exist" — is what this section covers.

**Precise definition:** **DNS caching** is the practice of a resolver storing a previously obtained answer and reusing it for subsequent identical queries, instead of repeating the resolution process. Every resource record ([§45](Section-45-Part6-DNS-Record-Types-A-AAAA-CNAME-MX-TXT-NS-SOA-SRV-PTR.md)) carries a **TTL (Time To Live)**, expressed in seconds, set by the zone's administrator, which tells any caching resolver the maximum duration it may serve that record from cache before it must be considered stale and re-fetched from the authoritative source. **Negative caching** extends this same idea to *failed* lookups: when a name genuinely doesn't exist (`NXDOMAIN`) or a specific record type doesn't exist for an otherwise valid name, resolvers cache that negative result too — governed not by the (nonexistent) record's TTL, but by a duration specified in the zone's `SOA` record's **minimum/negative-caching field**.

> 💡 **Tip:** TTL is a promise made by the zone owner about how long an answer is safe to reuse, not an enforced guarantee — a resolver that ignores TTL entirely and serves ancient cached data is behaving badly, but nothing in the protocol physically stops it. Treat TTL as a contract you author deliberately, not a knob that manages itself.

## 2. Why This Matters

- **TTL is the single biggest lever an infrastructure engineer has over how fast a DNS change takes effect in production**, and setting it correctly — low before a planned migration, higher for stability once settled — is a routine, high-leverage operational decision, not a set-and-forget default.
- **Negative caching explains a specific, confusing failure pattern**: a newly created record can appear to "not exist yet" for a period even after creation, because a resolver had already cached the prior `NXDOMAIN` answer for a name that didn't exist a moment ago.
- **Caching is what makes DNS's global query volume sustainable at all** — without it, the load implied by billions of devices repeatedly walking the full hierarchy for every lookup would be enormous; understanding this is core to understanding why DNS scales the way it does.
- **Cache behavior directly affects blue/green deployments, failover cutovers, and disaster recovery runbooks** — any procedure that depends on a DNS change taking effect "immediately" needs to account for the TTL that was in effect *before* the change, not the new TTL being set.
- **Misunderstanding caching is one of the most common sources of "it works for me but not for my colleague" DNS confusion**, since different resolvers hold independently aged cache entries for the exact same name at the exact same moment.

## 3. Prerequisites and Dependencies

This section directly extends [§45](Section-45-Part6-DNS-Record-Types-A-AAAA-CNAME-MX-TXT-NS-SOA-SRV-PTR.md) (record types, where TTL is introduced as a per-record field) and [§46](Section-46-Part6-Recursive-vs-Iterative-Resolution-Resolvers-and-Root-TLD-Authoritative-Servers.md) (recursive resolution, where the recursive resolver is identified as the party that actually performs and benefits from caching). It also assumes the `SOA` record mentioned briefly in [§45](Section-45-Part6-DNS-Record-Types-A-AAAA-CNAME-MX-TXT-NS-SOA-SRV-PTR.md), since the negative-caching TTL specifically comes from that record's fields rather than from any individual resource record. [§48](Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md) (Zone Files and Zone Transfers) shows exactly where TTL values are declared in real zone-file syntax, including the `SOA` record's minimum field this section discusses.

## 4. Architecture / Conceptual Diagram

```text
                  Positive Caching                          Negative Caching

  Client asks: A record for app.example.com     Client asks: A record for typo.example.com
        │                                              │
        ▼                                              ▼
  Resolver cache: MISS                           Resolver cache: MISS
        │                                              │
        ▼ (full iterative walk, §46)                   ▼ (full iterative walk, §46)
  Authoritative answer:                          Authoritative answer:
    app.example.com A 203.0.113.10 TTL=300          NXDOMAIN (name does not exist)
        │                                              │
        ▼                                              ▼
  Resolver caches the ANSWER for 300s            Resolver caches the FAILURE, using
        │                                          the zone's SOA "minimum" field (e.g. 60s)
        ▼                                              │
  Next query within 300s:                              ▼
  ────────────────────► Resolver cache: HIT       Next query within 60s:
  (no network traffic to authoritative server)    ────────────────────► Resolver cache: HIT
                                                   (still returns NXDOMAIN, even if the
                                                    record was created moments ago)
```

- **Positive and negative caching are governed by different TTL sources** — a real record's own TTL for positive answers, the zone's `SOA` minimum field for negative answers — which is why a freshly created record can still appear absent for up to that negative-caching window after creation.
- **Every resolver in the chain caches independently** — a client's OS-level stub resolver, an internal recursive resolver, and any upstream public resolver each maintain their own cache with their own remaining lifetime for the same answer, which is the real mechanism behind "propagation delay."
- **Lowering a TTL only helps *future* lookups performed after the lower TTL is itself observed and cached** — a resolver that already cached the record under the old, higher TTL will continue serving it for the remainder of that original TTL window regardless of any TTL change made afterward.

## 5. Hands-On

### 5.1 Observing a Record's Remaining TTL

**Purpose:** See exactly how much longer a resolver's cache will serve an answer before it must re-query — critical when timing a migration or cutover.

**Syntax:**

```bash
dig <domain> <TYPE>
```

**Example usage and expected output:**

```bash
$ dig app.example.com A

;; ANSWER SECTION:
app.example.com.       247     IN      A       203.0.113.10
```

**Production usage example:** Running this command against the same resolver a few seconds apart and watching the TTL count down (`247`, then `241`, then `235`...) is a quick, reliable way to confirm you're hitting a live cache rather than re-triggering a fresh lookup each time — useful for confirming caching behavior during a load test or before assuming a resolver is misbehaving.

**Common errors:** Querying different resolvers (or the authoritative server directly) between checks and expecting a consistent countdown is a mistake — each has an independently aged cache, so the number will not decrease predictably unless you query the exact same resolver each time.

### 5.2 Planning a TTL Reduction Before a Migration

**Purpose:** Minimize the window during which stale answers are served after a planned cutover, by lowering TTL well in advance.

**Syntax:**

```text
# Zone file / DNS provider console:
app.example.com.   3600   IN   A   203.0.113.10     # normal steady-state TTL

# Lower it well ahead of the planned change:
app.example.com.   60     IN   A   203.0.113.10     # short TTL, set 24-48h before cutover

# On cutover day, change the value while TTL is still low:
app.example.com.   60     IN   A   203.0.113.20     # new target, propagates within ~60s

# After confirming success, raise TTL back to a stable steady-state value:
app.example.com.   3600   IN   A   203.0.113.20
```

**Production usage example:** This is the standard runbook pattern for any planned DNS-based cutover (migrating a service to a new load balancer, changing cloud providers, executing a DR failover test) — the TTL reduction must happen *before* the actual value change, with enough lead time that every resolver that had cached the old, longer TTL has had a chance to expire and re-query under the new, shorter one.

**Common errors:** Lowering the TTL and changing the record value in the same maintenance window is a common mistake — resolvers that cached the record under the *old, longer* TTL will still serve the old value for the remainder of that original window, unaffected by the new lower TTL you just set, since they haven't re-queried yet to observe it.

### 5.3 Diagnosing a Suspected Negative-Cache Issue

**Purpose:** Confirm whether a newly created record is genuinely missing or just still shadowed by a cached `NXDOMAIN` from before it existed.

**Syntax:**

```bash
dig <domain> <TYPE> @<authoritative-server>   # bypass caching entirely
```

**Example usage and expected output:**

```bash
$ dig new-service.example.com A @ns1.example.com

;; ANSWER SECTION:
new-service.example.com. 300  IN      A       203.0.113.50
```

**Production usage example:** When a developer reports "the record I just created doesn't resolve," querying the authoritative server directly (bypassing every caching layer) immediately answers whether the record actually exists correctly (in which case the issue is a stale negative cache elsewhere that will clear on its own) or whether the record itself is genuinely misconfigured (in which case no amount of waiting will fix it).

**Common errors:** Concluding "DNS is broken" from a client-side lookup alone, without ever checking the authoritative server directly, leads to unnecessary troubleshooting of a problem that may simply be an expiring negative cache entry a short wait will resolve.

## 6. Production Usage Notes

- **TTL is a trade-off between agility and load, not a value to minimize universally.** Very low TTLs (single-digit seconds) increase resolution latency and query volume against authoritative servers for marginal responsiveness gain in most cases — reserve aggressively low TTLs for the specific, time-boxed window around a planned change, not as a permanent default.
- **Negative-cache TTL (the `SOA` minimum field) is easy to overlook when planning a "just-created record isn't resolving yet" investigation** — it is a distinct, separately configured value from any positive record's TTL, and defaults vary by DNS provider (some default to a few minutes, others longer).
- **Cloud DNS services ([§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md)) often expose TTL directly in their record-creation UI/API but obscure the negative-caching (`SOA` minimum) value inside a managed, less commonly edited zone-level setting** — worth locating explicitly in any provider you operate, since it directly affects how quickly a fixed typo or newly added record becomes visible.

## 7. Security Considerations

- **A resolver serving an answer well past its stated TTL (a misbehaving or deliberately misconfigured resolver) can mask an emergency DNS-based remediation** — for example, redirecting traffic away from a compromised endpoint via a DNS change won't take effect for clients stuck on an overly persistent stale cache, which matters directly for incident response planning.
- **Overly long negative-cache TTLs can be exploited to prolong a denial-of-service window** — if an attacker can trigger `NXDOMAIN` caching for a name right before a legitimate record is expected to appear there, clients may be denied service for the full negative-cache duration even after the real record is published.
- **Cache-poisoning defenses (randomized query IDs and source ports, DNSSEC validation, [§49](Section-49-Part6-DNSSEC-Chain-of-Trust-and-Threat-Model.md)) matter specifically because a poisoned cache entry persists and spreads its incorrect answer for the full remaining TTL**, not just for a single request — the longer the TTL, the longer a successful poisoning attack's effect lasts.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                | Resolution Path                                                                                             |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| A DNS change was made but old value is still returned intermittently   | Resolvers that cached the record under the previous TTL haven't expired yet | Wait out the original (pre-change) TTL window; confirm via direct authoritative query that the new value is correctly published |
| A newly created record returns `NXDOMAIN` for several minutes after creation | Negative caching of a prior lookup for the same name before it existed       | Query the authoritative server directly to confirm the record now exists; wait for the negative-cache TTL (`SOA` minimum) to expire elsewhere |
| Some users see the new value immediately, others don't for a long time | Different resolvers with different cache ages/policies for the same record  | Confirm the authoritative answer is correct; treat this as expected distributed-cache behavior, not a bug     |

## 9. Best Practices

- Proactively lower TTL well in advance (a full TTL cycle or more) of any planned DNS-dependent cutover, and only raise it back to a stable value after confirming the change has succeeded everywhere it needs to.
- Choose steady-state TTLs deliberately based on how often a record is expected to change and how tolerant the use case is of stale answers — a database endpoint that almost never changes can tolerate a much higher TTL than a load balancer front-end during an active migration period.
- When troubleshooting any "the record isn't resolving/isn't updated" report, always corroborate with a direct authoritative-server query before concluding there's a real configuration problem rather than an expected caching delay.

## 10. Common Anti-Patterns / Mistakes

- **Lowering a TTL at the same time as changing the record's value**, rather than well beforehand — this defeats the entire purpose of lowering TTL, since resolvers holding the old, longer TTL are unaffected by the change.
- **Setting every record to an extremely low TTL "to be safe," permanently.** This meaningfully increases load on authoritative servers and per-lookup latency for every client, for a benefit that's only actually needed during active change windows.
- **Ignoring negative-cache TTL entirely when planning a rollout of new records**, then being surprised when a subset of users see `NXDOMAIN` for a record that objectively exists at the authoritative source.

## 11. Interview Questions

**🎯 Beginner:** _"What does a DNS record's TTL control?"_
**Model answer:** TTL (Time To Live) is a value, in seconds, set on a DNS record that tells any caching resolver how long it's allowed to reuse that answer before it must ask the authoritative server again. A lower TTL means changes propagate faster but generates more query traffic; a higher TTL means less query traffic but slower propagation of changes.
_What the interviewer is probing for:_ Basic, correct understanding of what TTL actually governs.

**🎯 Intermediate:** _"What is negative caching, and why does it sometimes make a brand-new DNS record appear not to exist for a few minutes?"_
**Model answer:** Negative caching means a resolver remembers a *failed* lookup (like `NXDOMAIN` for a name that doesn't exist) for a period of time, governed by the zone's `SOA` record's minimum/negative-caching field, not by any individual record's TTL. If a resolver queried for a name before it was created and cached that `NXDOMAIN` result, it will keep returning "doesn't exist" for the remainder of that negative-cache window even after the record is actually published, since it hasn't re-queried yet to discover the new answer.
_What the interviewer is probing for:_ Whether the candidate knows negative caching exists as a distinct mechanism with its own TTL source, not just positive-record caching.

**🎯 Senior:** _"You're planning a DNS cutover for a production migration. Walk through your TTL strategy."_
**Model answer:** Well before the cutover — at least one full TTL cycle in advance — I'd lower the record's TTL to a short value, like 60 seconds, and let that change itself propagate and be observed by resolvers. Only once I'm confident resolvers have picked up the shorter TTL would I proceed with changing the actual record value on cutover day, since a resolver that cached the record under the old, longer TTL is unaffected by the TTL reduction until it naturally re-queries. After confirming the cutover succeeded and traffic has shifted correctly, I'd raise the TTL back to its normal steady-state value to reduce ongoing query load and latency, rather than leaving it permanently low.
_What the interviewer is probing for:_ Practical, sequenced understanding of TTL mechanics under real operational pressure — not just definitional knowledge, but the correct order of operations.

**🎯 Architect:** _"How would you design DNS TTL policy across an organization with hundreds of services, balancing agility against load on your DNS infrastructure?"_
**Model answer:** I'd set a tiered default TTL policy based on the volatility and criticality of each record class rather than a single organization-wide value: rarely changing infrastructure (root domain apex, mail records) gets a longer default TTL (hours) for stability and reduced query load; actively managed service endpoints, especially ones behind blue/green or canary deployment patterns, get a shorter default TTL (minutes) by default so routine changes propagate quickly without requiring a manual TTL-lowering step every time; and I'd bake an automated pre-change TTL-lowering step directly into any deployment pipeline that performs DNS cutovers, rather than relying on engineers to remember to do it manually. I'd also monitor query volume against authoritative/recursive infrastructure to catch cases where an overly aggressive low TTL is generating disproportionate load relative to how often that record class actually changes, and adjust the tiering over time based on that data.
_What the interviewer is probing for:_ Ability to design a TTL policy as a genuine trade-off system across an organization's diverse DNS records, including automating what junior engineers would otherwise have to remember manually.

## 12. Common Misconceptions

1. **"Lowering a TTL takes effect immediately for everyone."** It only takes effect once each resolver's already-cached answer (under the previous, longer TTL) naturally expires and it re-queries — the old TTL window still has to run out first.
2. **"TTL is the only thing governing how long a DNS answer is cached."** Negative (failure) answers are cached according to a completely separate value — the zone's `SOA` minimum field — not the TTL of any actual record.
3. **"DNS propagation delay" is a single, predictable, universal number.** In reality it's the maximum of many independently expiring caches across every resolver a client might use, bounded loosely by the previous TTL, but not a guaranteed or synchronized figure.
4. **"A resolver serving a slightly stale answer past its TTL is a protocol violation that will be caught and corrected automatically."** Nothing in DNS enforces TTL compliance; a misbehaving resolver serving stale data is a real, if uncommon, operational risk worth being aware of, not an impossibility.

## 13. 🔑 Key Takeaways

- TTL, set per record, tells caching resolvers how long they may reuse an answer before re-querying — it is the primary lever controlling propagation speed vs. query load.
- Negative caching remembers failed lookups (`NXDOMAIN`) using a separate value from the zone's `SOA` record, which is why a just-created record can appear absent for a window after creation.
- Because every resolver caches independently, "propagation delay" is really the combined effect of many separately expiring caches, not a single synchronized event.
- TTL should be lowered well in advance of a planned DNS change (not simultaneously with it), and raised back to a stable value once the change is confirmed successful.
- Diagnosing DNS resolution complaints should always include a direct authoritative-server query to establish ground truth before attributing a symptom to caching, propagation, or misconfiguration.

## 14. Related Concepts & What's Next

[§45](Section-45-Part6-DNS-Record-Types-A-AAAA-CNAME-MX-TXT-NS-SOA-SRV-PTR.md) introduced TTL as a per-record field and [§46](Section-46-Part6-Recursive-vs-Iterative-Resolution-Resolvers-and-Root-TLD-Authoritative-Servers.md) identified the recursive resolver as the party that performs and benefits from the caching this section details in full. [§48](Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md) shows exactly where TTL and the `SOA` minimum field are declared in real zone-file syntax. [§52](Section-52-Part6-DNS-Based-Load-Balancing-and-Failover-Patterns.md) (DNS-Based Load Balancing and Failover Patterns) depends directly on this section's TTL mechanics, since any DNS-based failover strategy's speed is fundamentally bounded by the TTL in effect on the records being changed.

**Next Section:** [§48](Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md) — `Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md`
