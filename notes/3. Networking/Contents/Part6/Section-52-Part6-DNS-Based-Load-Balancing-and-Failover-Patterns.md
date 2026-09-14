# Section 52 (Part 6): DNS-Based Load Balancing and Failover Patterns

## 1. Definition

**Plain language:** DNS can do more than point one name at one address — by returning different or multiple answers depending on health, location, or a rotation schedule, it can spread traffic across several servers or automatically steer clients away from a failed one, before the request ever reaches a dedicated load balancer.

**Precise definition:** **DNS-based load balancing** is the practice of an authoritative DNS server returning different answers for the same query — either multiple records in rotation (**round-robin DNS**) or a single record selected by policy (weighted, latency-based, geolocation-based) — to distribute client traffic across multiple backend endpoints without any traffic actually passing through the DNS infrastructure itself. **DNS-based failover** extends this with continuous **health checks** against each candidate endpoint, so that a record pointing at an unhealthy endpoint is automatically withdrawn from the answer set (or replaced with a designated failover target) until health is restored. Both techniques operate entirely at the resolution layer — the DNS answer determines *which* endpoint a client will connect to, but the actual load-bearing connection happens independently, over whatever transport the application uses.

> 💡 **Tip:** DNS-based load balancing and failover are fundamentally rate-limited by caching ([§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md)) — a client that already cached an answer under its TTL won't re-query and won't see a health-check-triggered change until that TTL expires. This single fact explains almost every practical limitation and design trade-off in this section.

## 2. Why This Matters

- **DNS-based traffic distribution is often the *first* layer of load balancing in a global architecture**, steering users to the nearest healthy region or data center before a regional load balancer (Part 9) takes over fine-grained distribution within that region — the two techniques are complementary, not competing.
- **DNS-based failover is frequently the mechanism behind multi-region disaster recovery**, since it operates above and independently of any single region's infrastructure — if an entire region's load balancers and servers become unreachable, DNS failover can redirect new connections to a surviving region without requiring any client-side reconfiguration.
- **Understanding TTL's role here directly determines how fast a failover actually completes in production** — a well-designed DR runbook accounts for the TTL that was in effect *before* an incident, not an idealized instantaneous cutover, which is a critical, sometimes painfully learned lesson during real outages.
- **Round-robin DNS has real, well-known limitations (no actual health awareness, uneven distribution due to caching) that make it insufficient on its own for most serious production traffic-distribution needs** — knowing exactly where it falls short is what justifies pairing it with health checks or a dedicated load balancer.
- **This is one of the most commonly asked system-design interview topics** ("how would you route users to the nearest data center," "how does global failover work") precisely because it sits at the intersection of DNS mechanics, latency, and availability engineering.

## 3. Prerequisites and Dependencies

This section is the natural capstone of Part 6, depending directly on [§45](Section-45-Part6-DNS-Record-Types-A-AAAA-CNAME-MX-TXT-NS-SOA-SRV-PTR.md) (multiple `A`/`AAAA` records enabling round-robin), [§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md) (TTL, which bounds how fast any DNS-based change is observed), and [§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md) (the managed cloud health-check-aware routing policies that implement most of this section's patterns in practice). It anticipates Part 9's Load Balancing content, particularly [§75](../Part9/Section-75-Part9-Health-Checks-and-Failover-Behavior.md) (health checks and failover behavior) and [§79](../Part9/Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md) (Global Server Load Balancing and Anycast), which cover the same failover and traffic-distribution goals from a dedicated-load-balancer and network-layer perspective rather than a purely DNS-layer one — the two Parts describe complementary techniques for the same underlying availability problem.

## 4. Architecture / Conceptual Diagram

```text
                DNS-Based Load Balancing and Failover — Layered Patterns

  1) ROUND-ROBIN (no health awareness)
     api.example.com   A   203.0.113.10
     api.example.com   A   203.0.113.11
     api.example.com   A   203.0.113.12
     ── Resolver returns all three (or rotates the order); client picks one,
        typically the first. No record is ever removed if its server dies.

  2) WEIGHTED ROUTING (traffic split by declared proportion)
     api.example.com  ──90%──►  203.0.113.10  (main fleet)
     api.example.com  ──10%──►  203.0.113.20  (canary fleet)

  3) LATENCY / GEOLOCATION ROUTING (answer depends on querier's location)
     api.example.com  ── us-east query ──►  203.0.113.10  (us-east region)
     api.example.com  ── eu-west query ──►  198.51.100.5  (eu-west region)

  4) HEALTH-CHECK-DRIVEN FAILOVER (answer changes based on live health)
     api.example.com  PRIMARY   203.0.113.10  ◄── health check: FAILING
                       │
                       ▼ (automatically withdrawn from answers)
     api.example.com  SECONDARY 198.51.100.99 ◄── health check: HEALTHY
                       (now the only, or primary, answer returned)

  ALL FOUR PATTERNS share the same hard limit: a client with an already-
  cached answer (§47) does not observe any of these changes until its
  local TTL expires and it re-queries.
```

- **Round-robin is the simplest pattern and the least capable** — it has no concept of server health, and because resolvers and clients may cache or reorder the returned set inconsistently, actual traffic distribution across the "round-robin" set is often far less even in practice than the name implies.
- **Health-check-driven failover is what turns DNS from a static map into an availability mechanism**, and it's the pattern most explicitly built into managed cloud DNS services ([§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md)), since it requires infrastructure (health-check probes) beyond what a plain authoritative nameserver provides.
- **Latency-based and geolocation routing both require the DNS service to know something about the querier's location** — typically inferred from the source IP of the *recursive resolver* making the request, not the end client directly, which is an important and sometimes surprising nuance (a client using a distant public resolver may get routed as if they were located near that resolver, not near themselves).

## 5. Hands-On

### 5.1 Observing Round-Robin DNS in Action

**Purpose:** See the simplest DNS load-balancing pattern directly, and observe its lack of health awareness.

**Syntax:**

```bash
dig <domain> +short
```

**Example usage and expected output:**

```bash
$ dig api.example.com +short
203.0.113.10
203.0.113.11
203.0.113.12

$ dig api.example.com +short     # a moment later — order may rotate
203.0.113.11
203.0.113.12
203.0.113.10
```

**Production usage example:** Round-robin DNS is still commonly used for simple, low-stakes distribution across a small, genuinely interchangeable fleet (a handful of stateless read replicas, for instance) where the operational simplicity outweighs the lack of health awareness — but it is rarely used alone for anything customer-facing and business-critical without a health-check layer on top.

**Common errors:** Assuming round-robin DNS provides automatic failover is a common and consequential mistake — if `203.0.113.10` in the example above goes down, it remains in the answer set indefinitely (subject only to however long the record itself persists) with no automatic removal, meaning roughly a third of new connections will keep failing until someone manually removes the record.

### 5.2 Configuring Health-Check-Driven Failover (AWS Route 53, Conceptual CLI)

**Purpose:** Implement the health-check-aware failover pattern described in the diagram, using a managed cloud DNS service's native capability.

**Syntax:**

```bash
aws route53 create-health-check --health-check-config \
  IPAddress=203.0.113.10,Port=443,Type=HTTPS,ResourcePath=/healthz,RequestInterval=30,FailureThreshold=3

# Then, a failover record set references that health check:
# api.example.com  PRIMARY  → 203.0.113.10  (associated with the health check above)
# api.example.com  SECONDARY → 198.51.100.99 (served automatically when PRIMARY is unhealthy)
```

**Example usage and expected output:**

```bash
$ dig api.example.com +short          # primary healthy
203.0.113.10

# ... primary fails health checks for 3 consecutive intervals (90s) ...

$ dig api.example.com +short          # after failover triggers
198.51.100.99
```

**Production usage example:** This is the standard pattern for active-passive multi-region disaster recovery — a primary region serves all traffic under normal conditions, and a secondary region (kept warm or scaled up on-demand) automatically becomes the DNS answer the moment the primary's health check fails, without requiring any manual intervention to initiate the failover itself.

**Common errors:** Setting the health check's `FailureThreshold`/`RequestInterval` too aggressively low can cause "flapping" — repeated failover and failback triggered by transient blips rather than genuine sustained outages — while setting them too high delays legitimate failover during a real incident; tuning this trade-off deliberately, based on the acceptable detection-to-failover time for the specific service, is a real design decision.

### 5.3 Calculating the Real-World Failover Time Bound

**Purpose:** Understand and communicate the actual, TTL-bounded speed of a DNS-based failover, rather than assuming it's instantaneous.

**Syntax:**

```text
Total observed failover time ≈
  health-check detection time (FailureThreshold × RequestInterval)
  + record TTL (worst case: a client cached the answer right before failure)
  + any additional resolver-chain caching delay
```

**Example usage and expected output:**

```text
Health check: 3 consecutive failures × 30s interval = 90s to detect
Record TTL: 60s

Worst case: a client resolved and cached the primary's IP 1 second
before it failed. That client will not see the new (secondary) answer
until: 90s (detection) + up to 60s (remaining TTL) ≈ up to 150s total.
```

**Production usage example:** This calculation belongs directly in any disaster-recovery runbook or RTO (Recovery Time Objective) commitment — quoting a DNS-based failover mechanism as achieving a specific RTO without accounting for both health-check detection time *and* the worst-case remaining TTL is a common and easily caught inaccuracy during DR plan review.

**Common errors:** Forgetting to account for clients that resolved and cached an answer moments *before* the failure (the worst case, using the *full* TTL, not an average) leads to overly optimistic failover-time estimates that don't hold up during an actual incident or DR test.

## 6. Production Usage Notes

- **DNS-based failover is best treated as a complement to, not a replacement for, load-balancer-level health checks and failover ([§75](../Part9/Section-75-Part9-Health-Checks-and-Failover-Behavior.md), Part 9)** — a regional load balancer already removes unhealthy individual servers from its own rotation in seconds; DNS-based failover operates one level up, at the region/data-center granularity, on a slower, TTL-bound timescale.
- **Anycast ([§79](../Part9/Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md), Part 9) is a network-layer alternative that sidesteps DNS's TTL limitation entirely** by routing the *same* IP address to the nearest healthy location at the BGP/routing layer — some organizations combine both techniques, using DNS-based routing for coarse geographic steering and Anycast for the fastest possible failover of a shared front-end IP.
- **Weighted and canary-style DNS routing is a legitimate but coarse-grained deployment technique** — because it operates at the level of "which server a given resolved client talks to for the TTL's duration," it lacks the fine-grained, per-request control that an application-layer load balancer or service mesh provides for canary rollouts, and is usually a complement to, not a substitute for, those tools.

## 7. Security Considerations

- **DNS-based failover targets should be kept warm and correctly configured at all times**, since a "cold" failover target that hasn't been validated recently can itself be broken exactly when it's needed most — untested failover paths are a classic disaster-recovery pitfall this pattern doesn't automatically prevent.
- **Health-check endpoints themselves can become a denial-of-service or manipulation target** — an attacker who can influence a health-check endpoint's response (if it's insufficiently protected or overly permissive) could potentially trigger unwanted failover events as a disruption technique, making the health-check path itself worth securing and monitoring.
- **Geolocation-based DNS routing decisions rely on IP-to-location mapping data that is not always perfectly accurate**, and should not be relied upon as a security or compliance control (e.g., for data-residency enforcement) without additional, more authoritative verification at the application layer.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                  | Resolution Path                                                                                                |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| A failed backend server keeps receiving new connections after going down | Plain round-robin DNS with no health-check integration                        | Add health-check-driven failover/routing, or move health-aware distribution to a dedicated load balancer         |
| Failover took much longer than expected during an incident              | Underestimated the combined health-check detection time plus worst-case TTL   | Recalculate and document the realistic failover time bound; consider lowering TTL or tightening health-check thresholds ahead of the next incident |
| Users in different regions report inconsistent routing behavior for the same name | Latency/geolocation routing is inferring location from the recursive resolver, not the end client, and users share a distant or misclassified resolver | Confirm which resolver each affected user is actually using; consider this a known limitation rather than a bug in most cases |

## 9. Best Practices

- Pair any DNS-based load-balancing or failover strategy with regularly tested failover targets — a secondary region or endpoint that's never actually received real traffic during a drill is a liability, not a safety net.
- Calculate and document the realistic, worst-case failover time (health-check detection window plus TTL) as part of any DR plan or SLA/RTO commitment, rather than assuming DNS-based failover is instantaneous.
- Use DNS-based routing for coarse, regional/data-center-level traffic steering, and rely on load balancers (Part 9) or a service mesh for finer-grained, faster-reacting distribution and failover within a region.

## 10. Common Anti-Patterns / Mistakes

- **Relying on plain round-robin DNS as the sole availability mechanism for a critical service**, with no health-check integration — a failed backend continues receiving a share of new connections indefinitely.
- **Quoting an unrealistically fast RTO for a DNS-based failover mechanism** without accounting for both health-check detection time and worst-case client-side TTL caching — a common gap discovered only during a real incident or a rigorous DR review.
- **Setting health-check thresholds so aggressively sensitive that transient, non-representative blips trigger full failover and failback cycles ("flapping")**, creating instability that's often worse than the brief issue the health check was meant to catch.

## 11. Interview Questions

**🎯 Beginner:** _"What is round-robin DNS, and what's its main limitation?"_
**Model answer:** Round-robin DNS is when a domain has multiple `A`/`AAAA` records pointing at different servers, and the DNS server returns them in rotating order, spreading new connections across the servers over time. Its main limitation is that it has no concept of server health — if one of the servers behind a round-robin record fails, DNS keeps returning its IP address just as often as the healthy ones, sending a share of new connections to a dead server until someone manually intervenes.
_What the interviewer is probing for:_ Correct basic understanding plus awareness of the specific, well-known gap (no health awareness) that motivates more advanced patterns.

**🎯 Intermediate:** _"Why can't DNS-based failover ever be truly instantaneous, even with a very responsive health-check system?"_
**Model answer:** Even if a health check detects a failure the instant it happens, any client that already resolved and cached the old answer under its TTL ([§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md)) will keep using that cached, now-stale answer until the TTL expires and it re-queries. So the real, worst-case failover time is the health-check detection time plus however much of the TTL window remains for the least-recently-refreshed client — it's never zero, and can't be, without either eliminating TTL entirely (at the cost of massively increased query load) or supplementing DNS-based failover with a network-layer technique like Anycast that doesn't depend on client-side caching at all.
_What the interviewer is probing for:_ Correctly connecting DNS-based failover's fundamental speed limit back to caching/TTL mechanics from earlier in the Part, rather than treating failover as a black box.

**🎯 Senior:** _"Design a DNS-based failover strategy for a service with a 5-minute RTO requirement. What would you actually configure?"_
**Model answer:** I'd work backward from the 5-minute budget: I need health-check detection time plus worst-case remaining TTL to fit comfortably under 5 minutes, with margin. I might set a health check with a 10-second interval and a 3-consecutive-failure threshold (30 seconds to detect), and set the record's TTL to something like 30-60 seconds — giving a worst-case bound of roughly 60-90 seconds, well within the 5-minute budget, with room to spare for any additional resolver-chain delay. I'd validate this isn't an aggressively low TTL causing excessive query load for the service's actual traffic volume, and I'd make sure the secondary/failover target is kept warm and is regularly tested with real failover drills, not just configured and left untouched — a theoretical failover path that's never actually been exercised is a common way RTO commitments quietly fail during a real incident.
_What the interviewer is probing for:_ Ability to translate an abstract RTO requirement into concrete health-check and TTL parameters, and awareness that configuration alone doesn't guarantee the RTO without regular testing.

**🎯 Architect:** _"How would you decide between DNS-based failover, Anycast, and a global load balancer for a multi-region, globally distributed service?"_
**Model answer:** I'd treat these as complementary layers addressing different granularities and speeds, not mutually exclusive choices. Anycast, where available (typically through a CDN or a cloud provider's global network product), gives the fastest possible failover because it operates at the routing layer and isn't subject to DNS caching delay at all — but it requires infrastructure and provider support that not every organization has direct access to, and works best for stateless, latency-sensitive front-end traffic. A global/GSLB-style load balancer ([§79](../Part9/Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md), Part 9) sits closer to a managed version of DNS-based routing with tighter health-check integration and sometimes faster reaction than raw DNS TTL allows. Plain DNS-based routing (weighted, latency, geolocation, with health-check failover) is the most broadly available and simplest to reason about option, appropriate when the RTO requirement is measured in minutes rather than seconds and the organization doesn't already have Anycast infrastructure. For most organizations without a CDN/Anycast platform already in place, I'd default to DNS-based health-check failover for coarse regional routing, paired with per-region load balancers for fine-grained, fast intra-region failover, and would only invest in Anycast if the RTO requirement genuinely couldn't be met any other way, given its higher infrastructure and provider-lock-in cost.
_What the interviewer is probing for:_ Nuanced, cost-aware architectural judgment about when each technique is actually justified, rather than reflexively recommending the most sophisticated (and expensive) option available.

## 12. Common Misconceptions

1. **"DNS-based failover happens instantly once a health check detects a problem."** It's bounded by both detection time and the worst-case remaining client-side TTL — never instantaneous, and the actual bound must be calculated, not assumed.
2. **"Round-robin DNS is a form of load balancing with failover built in."** It provides distribution, not failover — it has no health awareness and will keep returning a dead server's address indefinitely unless paired with a health-check mechanism.
3. **"Geolocation-based DNS routing routes based on the end user's actual physical location."** It routes based on the location associated with the *recursive resolver* making the query, which is often but not always close to the end client — a client using a distant public resolver can be routed as if located near that resolver instead.
4. **"DNS-based load balancing and a dedicated load balancer (Part 9) solve the same problem at the same layer."** DNS-based techniques determine which endpoint a client resolves to for a caching-bound period; a dedicated load balancer makes a fresh, health-aware routing decision on every single connection — they operate at different granularities and are typically used together, not as alternatives.

## 13. 🔑 Key Takeaways

- DNS-based load balancing (round-robin, weighted, latency/geolocation) and failover (health-check-driven) distribute or redirect traffic at the resolution layer, with the actual connection happening independently over whatever transport the application uses.
- Every DNS-based technique in this section is fundamentally bounded by caching and TTL ([§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md)) — no DNS-based change is observed by a client faster than its cached answer's remaining TTL allows.
- Round-robin DNS provides distribution but no health awareness on its own; health-check-driven failover is what makes DNS an actual availability mechanism.
- Realistic failover time must account for both health-check detection time and worst-case remaining TTL — quoting or assuming instantaneous DNS failover is a common and consequential planning mistake.
- DNS-based techniques are best used as a complementary, coarse-grained (regional/data-center) layer alongside dedicated load balancers (Part 9) and, where available, Anycast — not as a complete substitute for either.

## 14. Related Concepts & What's Next

[§47](Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md)'s TTL and caching mechanics are the direct, fundamental constraint on every technique in this section, and [§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md)'s managed cloud DNS health-check features are the concrete implementation vehicle for most of what's described here conceptually. [§75](../Part9/Section-75-Part9-Health-Checks-and-Failover-Behavior.md) (Part 9, Health Checks and Failover Behavior) and [§79](../Part9/Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md) (Part 9, Global Server Load Balancing and Anycast) pick up the same availability goals from a dedicated-load-balancer and network-layer perspective, completing the picture this section starts at the DNS layer. [§53](Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md), the final section of this Part, shifts from these traffic-management patterns to the practical diagnostic tools used to troubleshoot everything covered across Part 6.

**Next Section:** [§53](Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md) — `Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md`
