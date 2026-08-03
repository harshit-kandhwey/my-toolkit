# Part 4 - Section 6 - Amazon Route 53 - DNS

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: Route 53 is AWS's DNS service - it translates human-readable domain names into the IP addresses computers use to connect, and can also register domain names and make smart routing decisions based on health, location, or load.

Precise: Amazon Route 53 is AWS's highly available, scalable DNS web service, providing domain registration, DNS resolution, and traffic routing policies supporting health-check-based failover, geographic routing, and load distribution.

---

## 2. Why It Exists

- Every networked resource has an IP address, but IP addresses change - humans and applications need a stable name regardless of what IP currently backs it.
- Route 53 is the practical realization of Part 1's "global service" classification.
- Beyond simple resolution, Route 53's routing policies solve which of multiple healthy resources should handle a request - the nearest, healthiest, or a weighted split - the same problem weighted target groups solve at the load-balancer level, now at the DNS level, often working together.

---

## 3. DNS Fundamentals - Terminology

- Domain name - human-readable name identifying an internet resource.
- DNS record - an entry mapping a name to a value.
- Hosted zone - a container for DNS records for a specific domain - Route 53's core resource.
- Name servers (NS) - servers that actually answer DNS queries for a domain; your registrar must point to Route 53's assigned name servers.
- TTL (Time to Live) - how long a record's answer is cached before re-querying - lower TTL means faster propagation but more query volume; higher TTL reduces load but slows change propagation.

---

## 4. Record Types

- A - maps a name to an IPv4 address.
- AAAA - maps a name to an IPv6 address.
- CNAME - maps a name to another name - cannot be used at a zone's root/apex.
- Alias (Route 53-specific) - maps a name to an AWS resource (ALB, CloudFront, S3 website endpoint) - behaves like CNAME but CAN be used at the apex, and is free to query.
- MX - mail exchange, where email should be delivered.
- TXT - arbitrary text, commonly domain verification or SPF/DKIM.
- NS - name server records, defining zone/sub-zone authority.

Interview tip: CNAME can't be used at the zone apex due to DNS rules requiring other record types to coexist there. Route 53's Alias solves this - usable at the apex, points to AWS resources, no per-query charge.

---

## 5. Routing Policies

### 5.1 Simple Routing

One record, possibly multiple values, no logic (no health checks/weighting/geo-awareness) - appropriate for a single resource or client-side distribution logic.

### 5.2 Weighted Routing

Distributes traffic by assigned weights (70/30 split) - parallel to weighted target groups but at the DNS layer. Common for gradual migration/canary testing across entirely separate infrastructure stacks.

### 5.3 Latency-Based Routing

Routes to the AWS Region with lowest measured latency for the user - automates Region-selection-for-latency at the DNS layer for multi-Region apps.

### 5.4 Geolocation Routing

Routes based on query origin's geographic location (continent/country/state) - for location-appropriate content or compliance restrictions. Distinct from latency-based: geolocation is about content appropriateness, latency-based is about performance.

### 5.5 Geoproximity Routing

Routes based on resource AND user location, with a tunable bias value shifting traffic between regions - a more tunable geolocation variant for gradually shifting load.

### 5.6 Failover Routing

Routes to a primary resource by default, automatically failing over to a secondary if the primary fails its health check - a DNS-layer implementation of multi-Region DR, tied directly to Route 53 Health Checks (Section 6).

### 5.7 Multivalue Answer Routing

Returns multiple values (up to 8 healthy records) with basic health checking - lightweight availability improvement without full failover/weighted logic. Not a substitute for a real load balancer.

Key idea: each policy answers a different question - simple ("just this one"), weighted ("split by proportion"), latency-based ("fastest for this user"), geolocation ("appropriate content for location"), geoproximity ("shift load geographically, tunably"), failover ("primary unless down"), multivalue ("a few options, basic health awareness"). Choosing the wrong one is a common testable mistake.

---

## 6. Route 53 Health Checks

- Checks an endpoint's HTTP/HTTPS/TCP status and uses the result to influence routing (most directly Failover, but also excluding unhealthy endpoints from Weighted/Multivalue/Latency responses).
- Functionally distinct but conceptually parallel to ELB health checks - ELB checks determine targets behind one load balancer; Route 53 health checks determine which entire endpoints/Regions DNS points toward.
- Can also monitor CloudWatch alarms directly, reacting to any metric-driven condition, not just a direct HTTP/TCP check.

---

## 6a. AWS Global Accelerator - Network-Layer Global Routing

### 6a.1 Definition and the Problem It Solves

- AWS Global Accelerator routes user traffic to the optimal, healthy AWS endpoint (an ALB/NLB, or an EC2 instance/Elastic IP) using two static Anycast IP addresses, rather than DNS-based routing decisions.
- Core distinction from every Route 53 routing policy in Section 5: Route 53's policies operate at the DNS layer - a client resolves a name to an IP, and that resolution decision is subject to the client's own DNS caching and TTL behavior (Section 3). Global Accelerator operates at the network layer - traffic enters AWS's global network at the nearest edge location via the same static Anycast IPs regardless of client, and is then routed over AWS's private backbone to the optimal healthy endpoint, without depending on DNS resolution or caching behavior at all.

### 6a.2 Anycast IPs and Why They Matter

- Anycast means the same two IP addresses are announced from every AWS edge location globally - a user's traffic naturally routes to the nearest edge location at the network level (via standard internet routing, BGP), then travels the rest of the way to the actual endpoint over AWS's own backbone rather than the public internet.
- Because the IP addresses themselves never change (unlike Route 53 failover, which changes which IP a DNS query returns), Global Accelerator failover is not subject to DNS TTL/caching delays at all - a client that already has the Anycast IP continues sending traffic to it, and Global Accelerator itself redirects that traffic to a healthy endpoint internally, achieving faster failover than DNS-based failover routing can, precisely because there is no DNS record to wait to expire and re-resolve.

### 6a.3 Global Accelerator vs Route 53 Failover/Latency-Based Routing - The Decision

- Route 53 latency-based and failover routing (Section 5.3, 5.6) remain entirely valid, widely-used patterns, and are the right choice when DNS-layer routing is sufficient and the TTL-dependent propagation delay is acceptable for the application's actual requirements.
- Global Accelerator is the better fit specifically when: failover speed genuinely cannot tolerate DNS TTL/caching delay (some clients and resolvers do not respect TTL as strictly as expected, a real-world DNS caching inconsistency Global Accelerator sidesteps entirely), or when the application is not purely HTTP/HTTPS (Global Accelerator supports TCP and UDP generally, including non-web protocols, whereas CloudFront - Section 7 - is HTTP/HTTPS-specific).
- Interview tip: the cleanest way to frame this distinction is "Route 53 changes which IP a DNS answer returns; Global Accelerator keeps the IP constant and changes where traffic goes once it arrives" - a fundamentally different failover mechanism, not simply a faster version of the same one.

### 6a.4 Key Takeaways

1. Global Accelerator routes at the network layer using static Anycast IPs, distinct from Route 53's DNS-layer routing policies covered in Section 5.
2. Because the client-facing IP addresses never change, Global Accelerator failover avoids DNS TTL/caching propagation delay entirely - a genuinely faster failover mechanism than Route 53 failover routing for workloads that need it.
3. Global Accelerator supports general TCP/UDP traffic, not just HTTP/HTTPS - a relevant distinction versus CloudFront (Section 7), which is HTTP/HTTPS-specific.

## 7. Route 53 Resolver - DNS Within and Across VPCs

- The fuller capability behind every VPC's Amazon-provided DNS resolver (Section 1).
- Resolver Endpoints: Inbound lets on-premises systems (via VPN/Direct Connect) query the VPC's resolver for private AWS resource names; Outbound lets VPC resources forward queries to on-premises DNS servers for on-prem domain names.
- Resolver Rules determine which queries forward where (e.g., internal.corp.example.com forwards on-prem, everything else resolves normally).

---

## 8. Domain Registration

- Route 53 can act as a domain registrar (actually registering a domain) - a separate function from DNS hosting, though commonly used together.
- You can host DNS in Route 53 without registering the domain there, and vice versa - decoupled capabilities.

---

## 9. Production & Enterprise Usage

- Failover routing + health checks as the DNS-layer half of multi-Region DR (Part 10) - works alongside actual data replication/standby infrastructure, not instead of it.
- Hybrid DNS via Resolver Endpoints standard for mid-migration or permanent hybrid enterprises - consistent DNS experience regardless of resource location.
- Weighted routing for blue/green/canary at the infrastructure-stack level - complements load-balancer-level weighted target groups when comparing genuinely separate stacks/Regions/accounts.

---

## 10. Security Considerations

- DNS itself can be a target - Route 53 supports DNSSEC for cryptographic validation against tampered responses.
- Private hosted zones - resolvable only within specified VPCs, not publicly - avoids exposing internal naming/architecture to the public internet.
- Health check security - checkers query from known AWS IP ranges; security groups/NACLs must allow them or health checks fail.

---

## 11. Performance Considerations

- TTL tuning is a real trade-off - low TTL enables fast failover/changes but increases query volume; high TTL reduces load but slows propagation.
- Latency-based routing accuracy depends on AWS's own latency measurements - reliable but a measured approximation, not a per-path guarantee.

---

## 12. Troubleshooting

| Symptom                                                | Cause                                            | Fix                                                                         |
| ------------------------------------------------------ | ------------------------------------------------ | --------------------------------------------------------------------------- |
| DNS changes not taking effect for some users           | Previous TTL still cached                        | Wait out the TTL, or lower TTL proactively before planned changes           |
| CNAME fails at the zone apex                           | CNAME can't be used at the apex                  | Use a Route 53 Alias record instead                                         |
| Failover routing not failing over despite primary down | Health check misconfigured or blocked by SG/NACL | Verify health check config and allow Route 53 health-checker IP ranges      |
| On-prem can't resolve private AWS names                | No Inbound Resolver Endpoint configured          | Set up an Inbound Resolver Endpoint, configure on-prem DNS to forward to it |

---

## 13. Best Practices & Anti-Patterns

Best practices: use Alias records instead of CNAMEs for AWS resources, especially at the apex; choose the routing policy matching the actual requirement; lower TTLs proactively before planned migrations/failovers; use private hosted zones for internal-only naming; allow health-checker IP ranges through firewalls.

Anti-patterns: using CNAME at the zone apex; confusing geolocation with latency-based routing; leaving TTLs high on records needing fast failover; forgetting to allow health-checker traffic through firewalls.

---

## 14. Common Misconceptions

- "CNAME and Alias are basically the same." False - CNAME can't be used at the apex and incurs query charges; Alias can be used at the apex and is free for AWS resource targets.
- "Geolocation and latency-based routing solve the same problem." False - content-appropriateness vs performance.
- "Route 53 health checks are the same as ELB health checks." False - different layers (DNS endpoint/Region health vs load-balancer target health).
- "You must register your domain through Route 53 to use it for DNS." False - hosting and registration are decoupled.

---

## 15. Interview Questions (with model answers)

Beginner - Difference between CNAME and Route 53 Alias record? CNAME maps to another name but can't be used at the zone apex. Alias is Route-53-specific, usable at the apex, points directly to AWS resources, and has no per-query charge.

Beginner - Difference between geolocation and latency-based routing? Geolocation directs by query origin for content-appropriateness/compliance reasons. Latency-based directs to whichever Region gives lowest measured latency, purely for performance - can produce different results for the same user.

Intermediate - How does Route 53 Failover routing implement DR, and what else does it depend on? Directs to a primary by default; health check failure shifts DNS responses to the secondary. Only handles DNS-layer redirection - depends entirely on the secondary actually being ready (data replication, standby infrastructure, application readiness already in place). Failover routing is the redirection mechanism, not the DR strategy itself.

Intermediate - Inbound Resolver Endpoint exists but on-prem still can't resolve private AWS names - what to check? Whether on-prem DNS servers are actually configured to forward relevant queries to the endpoint's IPs - existence alone doesn't mean on-prem DNS knows to use it. Also check hybrid connectivity (VPN/Direct Connect) reaches the endpoint, and security groups allow the DNS traffic.

Senior - Design Route 53 strategy for a global app: US/EU/Asia users, performance optimization plus EU data-residency requirement (EU users only served by EU infra)? Layered combination, not one policy. Geolocation routing as outermost layer for EU-originated queries, hard-routing only to EU infrastructure (data residency as a rule, not preference). Latency-based routing between US and Asia endpoints for non-EU users, optimizing performance where no hard constraint exists. Failover routing layered under each geographic/latency choice, so unhealthy primaries fail over within the appropriate option set (EU users to another EU-compliant option, others to next-best latency). Hard compliance guarantee for EU, performance optimization everywhere else.

---

## Key Takeaways

1. Route 53 is more than name resolution - domain registration, DNS hosting, and differentiated routing policies (simple, weighted, latency-based, geolocation, geoproximity, failover, multivalue) each answering a different traffic-distribution question.
2. Alias records solve CNAME's zone-apex limitation and are free to query for AWS resource targets - a frequently tested detail.
3. Geolocation (content-appropriateness) and latency-based (performance) routing are commonly confused but solve genuinely different problems.
4. Route 53 Failover routing is the DNS-layer traffic-redirection half of a DR strategy, not the whole strategy - depends entirely on the secondary actually being ready.
5. Route 53 Resolver Endpoints extend DNS resolution across hybrid environments - Inbound for on-prem querying AWS, Outbound for AWS querying on-prem, connecting Section 5's hybrid connectivity to this section's naming layer.

## Related Concepts (forward links)

- CloudFront CDN, which frequently uses Route 53 and works alongside its routing policies -> §35
- AWS Global Accelerator, a complementary network-layer alternative to DNS-based routing/failover (see Section 6a above) -> §34a
- Multi-Region DR patterns using Failover routing as one component -> Part 10
- VPC Endpoints, Flow Logs, and network troubleshooting tools -> §37
