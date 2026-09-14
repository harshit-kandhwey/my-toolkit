# Section 74 (Part 9): Load-Balancing Algorithms: Round Robin, Least Connections, Weighted, Hashing

## 1. Definition

**Plain language:** Once a load balancer has a pool of healthy backends to choose from, it still needs a rule for picking exactly which one gets each new request. That rule is the algorithm. The simplest just cycles through backends in order; smarter ones account for how busy each backend currently is, how powerful each backend is relative to the others, or deliberately send the same client to the same backend every time.

**Precise definition:** A **load-balancing algorithm** is the deterministic or probabilistic function a load balancer applies, at the moment of selecting a backend for a new connection or request, over the current set of healthy pool members. The most common families are: **round robin** (cycle through backends in fixed order), **weighted round robin** (cycle through backends, but give some a proportionally larger share based on an assigned weight), **least connections** (send the new request to whichever backend currently has the fewest active connections), **weighted least connections** (least connections adjusted by a capacity weight), and **hash-based** methods (deterministically map a property of the request — client IP, a cookie, a URL — to a specific backend, so the same input consistently maps to the same backend). The choice of algorithm directly determines how evenly load is spread and whether a given client's requests reliably land on the same backend.

> 💡 **Tip:** There is no universally "best" algorithm — the right choice depends entirely on backend homogeneity (are all backends the same size?) and workload shape (are requests uniform, or wildly variable in cost?). Least connections generally outperforms round robin whenever request duration varies significantly between requests; round robin is simpler and sufficient whenever requests are roughly uniform in cost and backends are identical.

## 2. Why This Matters

- **The wrong algorithm produces uneven load even with healthy backends and correct health checks.** Plain round robin sending equal request *counts* to backends that take wildly different amounts of time to process each request will still overload the slower backend, since "equal count" is not the same as "equal load."
- **Session-sensitive architectures depend on hash-based algorithms to work at all.** Applications that don't share session state across backends ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md) covers this trade-off) need requests from the same client to consistently land on the same backend, which round robin and least connections cannot guarantee but IP-hash or cookie-hash can.
- **Heterogeneous backend fleets require weighting to avoid wasting or overloading capacity.** A mixed fleet with some larger and some smaller instances (common during a gradual instance-type migration, or when new nodes are added mid-scale-out) needs weighted algorithms so the larger nodes take a proportionally larger share.
- **Algorithm choice is a real, named configuration option in every load balancer product**, cloud-managed and software alike — understanding what each option actually does (rather than picking one by name recognition) is directly applicable to real configuration work.
- **Canary and gradual rollout patterns are implemented using weighting.** Shifting 5%, then 25%, then 100% of traffic to a new backend version during a deployment is a direct application of weighted algorithms, connecting this section to real deployment practice.

## 3. Prerequisites and Dependencies

This section assumes the backend pool and health-check concepts introduced in [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md) — an algorithm only ever selects among backends that health checks ([§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md)) have already determined are eligible to receive traffic. It also assumes the Layer 4/Layer 7 distinction from [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md), since some algorithms (like connection-based hashing) behave differently depending on which layer the load balancer operates at. [§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md) builds directly on the hash-based algorithms introduced here, since sticky sessions are typically implemented as a specific application of consistent hashing or cookie-based routing.

## 4. Architecture / Conceptual Diagram

```text
   ROUND ROBIN                    LEAST CONNECTIONS              WEIGHTED (2:1:1)
   (fixed cyclic order)           (fewest active conns wins)     (proportional share)

   Req1 ► Backend A                Backend A: 3 active            Backend A (weight 2)
   Req2 ► Backend B                Backend B: 7 active     ►      gets ~50% of traffic
   Req3 ► Backend C                Backend C: 1 active ◄── chosen Backend B (weight 1)
   Req4 ► Backend A (cycle)                                       gets ~25%
   Req5 ► Backend B               New request goes to C           Backend C (weight 1)
                                   regardless of cycle order       gets ~25%

   HASH-BASED (e.g., source IP hash)
   ──────────────────────────────────────────────────
   hash(client_ip) mod N  ──►  always same backend for
                                 that client, as long as
                                 pool size N is unchanged

   Client 10.0.0.5  ──hash──►  Backend B  (every request, every time)
   Client 10.0.0.9  ──hash──►  Backend A  (every request, every time)
```

- **Round robin** requires the least state to implement — just a rotating pointer — but assumes uniform request cost and uniform backend capacity, both of which are frequently false in production.
- **Least connections** requires the load balancer to track live connection counts per backend in real time, which is straightforward for a Layer 4/proxy-mode load balancer that terminates connections, but naturally reflects actual current load rather than a blind rotation.
- **Hash-based algorithms** trade even distribution for determinism — a skewed input distribution (a few very "hot" client IPs or cache keys) can produce uneven backend load even though the hash function itself is uniform, because the underlying input isn't.
- Changing pool size (adding or removing a backend) **disrupts naive hashing** — `hash(x) mod N` remaps almost every key when `N` changes, which is exactly the problem **consistent hashing** is designed to minimize by only remapping a small fraction of keys on a pool size change.

## 5. Hands-On

### 5.1 Configuring Weighted Round Robin in NGINX

**Purpose:** Show how to give a more powerful backend a proportionally larger share of traffic using explicit weights.

**Syntax:**

```nginx
upstream backend_pool {
    server 10.0.1.10:8080 weight=3;
    server 10.0.1.11:8080 weight=1;
    server 10.0.1.12:8080 weight=1;
}
```

**Example usage and expected output:**

```bash
$ for i in $(seq 1 10); do curl -s http://lb.internal/health | jq -r .served_by; done
10.0.1.10
10.0.1.10
10.0.1.11
10.0.1.10
10.0.1.12
10.0.1.10
10.0.1.10
10.0.1.11
10.0.1.10
10.0.1.12
```

- `10.0.1.10` (weight 3) receives roughly three times the requests of the other two backends (weight 1 each) across a large enough sample, though NGINX's default weighted round robin interleaves requests rather than sending three in a row.

**Production usage example:** Weighted round robin is the standard mechanism for canary deployments — a new version starts at `weight=1` alongside an established version at `weight=99`, receiving roughly 1% of traffic, with the weight increased gradually as confidence grows, all without any code deployment change to the routing logic itself.

**Common errors:** Forgetting that weights are *relative*, not absolute percentages — `weight=3` and `weight=1` produce the same 3:1 ratio as `weight=30` and `weight=10`; a common mistake is assuming a weight value maps directly to a percentage of total traffic without accounting for the sum of all weights in the pool.

### 5.2 Configuring Least Connections in HAProxy

**Purpose:** Demonstrate load balancing that adapts to real-time backend load rather than blindly cycling, appropriate when request durations vary significantly.

**Syntax:**

```
backend app_pool
    balance leastconn
    server app1 10.0.1.10:8080 check
    server app2 10.0.1.11:8080 check
    server app3 10.0.1.12:8080 check
```

**Example usage and expected output:**

```bash
$ echo "show stat" | socat stdio /var/run/haproxy.sock | cut -d, -f1,2,5
app_pool,app1,4
app_pool,app2,12
app_pool,app3,3
```

- HAProxy's admin socket shows the current active connection count (`scur`, column 5 here) per backend server — with `leastconn`, the next new connection is routed to `app3`, the backend with the fewest active connections at that instant, regardless of how many total connections each has historically received.

**Production usage example:** Least connections is the standard choice for backends handling requests of highly variable duration — a mix of fast health-check-style endpoints and slow report-generation endpoints on the same pool, for instance — where round robin would otherwise pile long-running requests onto whichever backend happens to be next in the cycle.

**Common errors:** `leastconn` measures *connection count*, not actual CPU load or resource utilization — a backend can have very few connections but be pegged at 100% CPU on a single expensive request, and `leastconn` has no visibility into that; for workloads where connection count doesn't correlate well with real load, this algorithm can still produce uneven load in practice.

### 5.3 Source-IP Hash-Based Routing for Session Affinity

**Purpose:** Ensure a given client consistently reaches the same backend without relying on cookies, useful for stateful protocols or when cookie-based persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) isn't available.

**Syntax:**

```nginx
upstream backend_pool {
    ip_hash;
    server 10.0.1.10:8080;
    server 10.0.1.11:8080;
    server 10.0.1.12:8080;
}
```

**Example usage and expected output:**

```bash
$ for i in $(seq 1 5); do curl -s --interface eth0 http://lb.internal/health | jq -r .served_by; done
10.0.1.11
10.0.1.11
10.0.1.11
10.0.1.11
10.0.1.11
```

- Every request from this client's source IP consistently maps to the same backend (`10.0.1.11`), regardless of request count — this persists as long as the pool membership itself doesn't change.

**Production usage example:** IP-hash routing is commonly used for stateful TCP protocols and for clients behind a NAT gateway sharing one apparent source IP, where cookie-based session persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) isn't applicable because the protocol isn't HTTP at all.

**Common errors:** Many clients behind the same corporate NAT or mobile carrier NAT share a single visible source IP, which `ip_hash` will pin to one backend for all of them — this can create severe, unexpected load imbalance for services with a large fraction of NAT'd clients, a known limitation worth checking before relying on IP hashing at scale.

## 6. Production Usage Notes

- **Least connections is the more robust default for HTTP APIs with variable request cost**, and round robin remains perfectly adequate for uniform, fast, stateless request patterns — defaulting to round robin everywhere "because it's simplest" leaves real performance on the table for variable workloads.
- **Weighted algorithms are the mechanism, not the policy, behind canary and blue/green deployments** — the deployment tooling adjusts weights over time, but the underlying load-balancing behavior is exactly the weighted round robin or weighted least connections mechanism described here.
- **Adding or removing pool members changes hash-based routing outcomes for most or all clients**, not just the ones directly affected by the change — this is a structural property of naive hashing and is the reason consistent hashing implementations exist in products that need to minimize this disruption (e.g., some CDN and cache-routing layers).

## 7. Security Considerations

- Hash-based routing keyed on a client-controllable value (like a request header the client sets) can be abused to deliberately target a specific backend, which is a consideration for any security-sensitive routing decision — routing keys should generally be based on values the load balancer itself determines (verified source IP, session cookie it issued) rather than arbitrary client-supplied input.
- An algorithm that concentrates traffic predictably (weighted routing sending a fixed 90% to one backend, for instance) creates a more attractive, higher-impact target for a resource-exhaustion attack against that specific backend than an algorithm that spreads load unpredictably — this is a minor but real consideration in threat modeling for high-value backends.
- Uneven load distribution from a poorly chosen algorithm can itself become a self-inflicted denial-of-service condition, where one backend is pushed into failure by the routing algorithm rather than by external attack traffic at all.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                | Resolution Path                                                                                                     |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| One backend consistently more loaded than others despite equal weights | Requests vary significantly in cost and the algorithm is round robin, not least connections    | Switch to `leastconn`/least-connections algorithm if request durations are non-uniform                              |
| A specific client always hits the same backend, even when it's overloaded | Hash-based (IP hash or similar) routing is in effect, pinning that client's traffic             | Confirm whether persistence/hashing is required for the workload ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)); if not, switch to round robin/least connections |
| Traffic distribution doesn't match configured weights               | Weights misunderstood as absolute percentages, or weight values not actually applied/reloaded  | Recalculate intended ratio relative to sum of all weights; confirm configuration reload actually took effect         |
| A large fraction of traffic lands on one backend after a NAT-heavy client base grows | IP-hash algorithm pinning many distinct users sharing one NAT'd source IP to a single backend   | Move away from IP hash for HTTP workloads in favor of cookie-based persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) which distinguishes users individually |

## 9. Best Practices

- Default to least connections for HTTP/API workloads with variable request cost, and reserve round robin for genuinely uniform, low-variance workloads where its simplicity is a benefit rather than a limitation.
- Use weighted algorithms deliberately and explicitly for heterogeneous backend fleets or gradual rollouts, and document what the weight values represent so a future engineer doesn't misinterpret them as fixed percentages.
- Reach for hash-based routing only when session affinity or protocol constraints genuinely require it, and prefer cookie-based persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) over IP-hash for HTTP workloads where the risk of NAT-related traffic skew is a concern.

## 10. Common Anti-Patterns / Mistakes

- **Using IP-hash-based persistence for HTTP workloads by default "for stickiness," without considering NAT-related skew.** Cookie-based persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) is almost always the better choice for HTTP traffic specifically because it identifies individual clients rather than shared network addresses.
- **Assuming weighted round robin values are literal percentages.** Weights are relative to the sum of all weights in the pool — a common configuration bug is setting weights that don't produce the intended traffic split because this relative math wasn't accounted for.
- **Never revisiting algorithm choice as workload characteristics change.** An algorithm chosen when a service had uniform, fast requests can become the wrong choice once the service grows to include slow, variable-cost endpoints on the same pool — algorithm choice deserves periodic reassessment, not a one-time decision at initial setup.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between round robin and least connections load balancing?"_
**Model answer:** Round robin cycles through backends in a fixed order, sending each new request to the next backend in line regardless of how busy any of them currently are. Least connections looks at how many active connections each backend currently has and sends the new request to whichever backend has the fewest, adapting to real-time load rather than following a blind rotation.
_What the interviewer is probing for:_ Basic recall of the two most common algorithms and the practical difference in behavior between them.

**🎯 Intermediate:** _"When would round robin actually perform worse than least connections, even with identical, healthy backends?"_
**Model answer:** When request duration varies significantly — for example, a mix of fast health-check-style requests and slow, expensive report-generation requests hitting the same pool. Round robin sends an equal *count* of requests to each backend, but if one backend happens to get a disproportionate share of the slow requests purely by the luck of the rotation order, it ends up carrying much more actual load than the others despite receiving the 'same number' of requests. Least connections avoids this because it reacts to how many requests are actually still in flight on each backend at the moment of the routing decision, not just a count of past assignments.
_What the interviewer is probing for:_ Understanding that "equal request count" and "equal load" are different things, and that algorithm choice should match workload characteristics.

**🎯 Senior:** _"Your team wants session affinity for an HTTP service. Would you use IP-hash based routing or cookie-based persistence, and why?"_
**Model answer:** I'd default to cookie-based persistence for an HTTP service. IP-hash routes based on the client's source IP, but many real clients share a source IP through NAT — corporate networks, mobile carrier NAT, some VPNs — which means IP-hash can inadvertently pin a large group of genuinely distinct users to a single backend, creating uneven load that has nothing to do with actual per-user traffic patterns. Cookie-based persistence identifies the individual client session directly, regardless of shared network addressing, and is the mechanism purpose-built for HTTP session affinity. I'd reserve IP-hash for non-HTTP protocols where cookies aren't available at all, or in the rare case where I specifically need to route by network origin rather than by session.
_What the interviewer is probing for:_ Awareness of the NAT-skew failure mode of IP-hash and the ability to choose the mechanism that matches the actual protocol and use case.

**🎯 Architect:** _"You're rolling out a new version of a service using weighted routing for a canary deployment, gradually shifting from 1% to 100% traffic on the new version over several hours. What could go wrong with this approach purely from an algorithm-behavior standpoint, independent of the new version's actual code quality?"_
**Model answer:** A few algorithm-level risks: first, if the load balancer's weighted round robin is coarse-grained or the traffic volume is low, a 1% weight might translate to bursty, uneven actual traffic to the canary rather than a smooth 1% stream, making early canary metrics noisy and harder to trust. Second, if session persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) is also configured on this pool, clients already pinned to the old version's backends by a sticky cookie won't be affected by the weight change at all until their session ends or the persistence expires — meaning the rollout appears to progress by weight but real user exposure lags significantly behind the configured percentage, which can mask or delay detection of a canary regression. Third, if the algorithm is least connections rather than weighted round robin, a canary backend that happens to process requests faster than the old version could end up receiving disproportionately more traffic than its configured weight implies, since least connections reacts to real-time load rather than respecting a fixed ratio — the two algorithm types don't combine as cleanly as they might appear to on paper, and I'd verify which one is actually active before trusting the weight percentages as ground truth.
_What the interviewer is probing for:_ Deep, mechanism-level understanding of how algorithm choice interacts with session persistence and real-time load signals, beyond the surface-level "just shift the weight" description of canary deployments.

## 12. Common Misconceptions

1. **"Round robin guarantees equal load across backends."** It guarantees equal request *count* distribution over time, not equal actual load, which diverges whenever request cost is non-uniform.
2. **"Weighted round robin percentages are exact and absolute."** Weight values are relative to the sum of weights in the pool, and actual short-term traffic distribution can still show variance around the target ratio depending on implementation.
3. **"IP-hash and cookie-based persistence are interchangeable ways to achieve the same thing."** They key on fundamentally different identifiers (network address vs. individual session) and have different failure modes — IP-hash suffers from NAT-related skew that cookie-based persistence does not.
4. **"Least connections is always the best choice."** It reacts to connection count, not actual resource utilization (CPU, memory) — for workloads where connection count doesn't correlate with real backend load, it can still produce uneven results, and a simpler algorithm may be just as effective with less complexity.

## 13. 🔑 Key Takeaways

- Round robin cycles evenly by request count; least connections reacts to real-time active connection counts; weighted variants of both bias distribution toward specific backends; hash-based algorithms deterministically pin a given input to a specific backend.
- Algorithm choice should match workload shape — least connections for variable-cost requests, round robin for uniform ones, weighted for heterogeneous fleets or gradual rollouts, hashing for session affinity or protocol constraints.
- IP-hash routing risks uneven load from NAT'd clients sharing a source IP; cookie-based persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) avoids this for HTTP workloads by identifying individual sessions directly.
- Weighted routing is the underlying mechanism behind canary and gradual rollout deployment patterns, not a separate feature.
- Hash-based routing is disrupted by pool size changes unless the implementation specifically uses consistent hashing to minimize remapping.

## 14. Related Concepts & What's Next

[§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md) covers the health-checking mechanism that determines which backends are even eligible for an algorithm to select among, extending the "healthy backends only" assumption made throughout this section. [§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md) builds directly on the hash-based and cookie-based routing concepts introduced in §5.3 into a full treatment of sticky sessions and their trade-offs. [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md) is worth revisiting for how algorithm implementation differs depending on whether the load balancer operates at Layer 4 or Layer 7.

**Next Section:** [§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md) — `Section-75-Part9-Health-Checks-and-Failover-Behavior.md`
