# Section 50 (Part 6): Split-Horizon / Split-View DNS

## 1. Definition

**Plain language:** Sometimes the same domain name needs to resolve to a *different* answer depending on who's asking — an internal employee on the corporate network should reach a service's private, internal IP address directly, while an external customer hitting the same name should be routed through a public load balancer. Split-horizon DNS is the technique of serving different answers for the same name depending on where the query is coming from.

**Precise definition:** **Split-horizon DNS** (also called **split-view** or **split-brain DNS**) is a configuration in which an authoritative DNS server (or a set of them) maintains two or more distinct **views** of the same zone — or entirely separate zones sharing the same name — and selects which view to answer from based on the querier's characteristics, most commonly their source IP address or which network they're querying from. The same domain name, `internal-api.example.com`, might resolve to `10.0.1.15` for a client inside the corporate VPN or VPC, and to a public-facing IP (or `NXDOMAIN`, if the name shouldn't be externally visible at all) for a client outside it.

> 💡 **Tip:** Split-horizon DNS is not a security control on its own — it's a convenience and routing-optimization mechanism. Never assume that because a record is only served on the "internal" view, it's actually protected from external discovery or access; the underlying resource still needs its own access controls (security groups, firewalls) regardless of which DNS view can see its name.

## 2. Why This Matters

- **Split-horizon DNS is the standard technique behind "internal load balancer, same hostname" patterns** in cloud environments — an application team often wants `api.example.com` to route internal service-to-service traffic over a private, lower-latency path while external users get the public-facing path, without maintaining two different hostnames.
- **Hybrid and multi-region architectures rely on it for locality-aware answers** — a corporate network with offices in multiple regions can use split-horizon to route each office's traffic to its geographically nearest internal resource under one shared internal naming scheme.
- **It directly explains a very common and otherwise confusing troubleshooting symptom**: "this works when I'm on the VPN/office network but not from home," which is often not a bug at all, but split-horizon DNS correctly returning a different (and, from outside the intended network, unreachable) answer.
- **Getting split-horizon configuration wrong is a frequent source of real incidents** — an internal-only view accidentally becoming the default answer for external queriers (or vice versa) can silently misroute production traffic in a way that's hard to detect until an external user reports a failure.
- **Understanding this pattern is prerequisite to correctly interpreting cloud-native private DNS zones** ([§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md)), since AWS Route 53 Private Hosted Zones, Azure Private DNS Zones, and GCP Cloud DNS private zones are all managed implementations of exactly this split-horizon concept.

## 3. Prerequisites and Dependencies

This section builds on [§44](Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)'s zone/namespace concepts (a split-horizon setup is, structurally, two or more zones or views sharing the same name) and [§46](Section-46-Part6-Recursive-vs-Iterative-Resolution-Resolvers-and-Root-TLD-Authoritative-Servers.md)'s resolver model, since the "view selection" logic operates at the point where a query arrives at a resolver or authoritative server. It's also useful to have read [§45](Section-45-Part6-DNS-Record-Types-A-AAAA-CNAME-MX-TXT-NS-SOA-SRV-PTR.md)'s record types, since the actual content that differs between views is ordinary `A`/`AAAA`/`CNAME` records — split-horizon changes *which* records are served, not the record types themselves. [§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md) (DNS in Cloud Environments) is the direct continuation of this section, showing how major cloud providers implement split-horizon as a managed "private hosted zone" feature.

## 4. Architecture / Conceptual Diagram

```text
                    Split-Horizon DNS: One Name, Two Views

                              Query: "api.example.com"
                                        │
                     ┌──────────────────┴──────────────────┐
                     ▼                                      ▼
           Query arrives from INSIDE                Query arrives from OUTSIDE
           the corporate network/VPC                the corporate network/VPC
                     │                                      │
                     ▼                                      ▼
         ┌───────────────────────┐              ┌───────────────────────┐
         │  INTERNAL VIEW         │              │  EXTERNAL VIEW         │
         │  api.example.com       │              │  api.example.com       │
         │    A  10.0.1.15        │              │    A  203.0.113.80     │
         │  (private VPC IP,      │              │  (public load balancer,│
         │   direct, low-latency) │              │   goes through WAF/LB) │
         └───────────────────────┘              └───────────────────────┘

  Same authoritative name server infrastructure (or a DNS provider's
  "private zone" feature) — the DIFFERENCE is which view answers, decided
  by where the query originates, not by anything in the query itself.
```

- **View selection typically happens at the network/DNS-server-address level, not per-query inspection of content.** A client is routed to the "internal" view simply because it's querying a resolver only reachable from inside the private network (a VPC's internal resolver, or an internal-only nameserver address) — the split is enforced by network topology and routing, not by the DNS protocol itself inspecting who's asking.
- **The two views can be entirely separate zone files/configurations on the same server software**, or literally two different servers (an internal-only nameserver and a public-facing one) that happen to be authoritative for the same name — both are valid implementations of the same underlying pattern.
- **Cloud-native implementations ([§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md)) associate a "private" view with a specific VPC/VNet directly**, rather than relying on network-path-based access as the sole differentiator — a more explicit and typically more secure mechanism than pure IP-based view selection on self-managed nameservers.

## 5. Hands-On

### 5.1 Configuring Split Views in BIND

**Purpose:** See the concrete server-side configuration mechanism (BIND's `view` statement) that implements split-horizon on self-managed DNS infrastructure.

**Syntax:**

```text
view "internal" {
    match-clients { 10.0.0.0/8; 192.168.0.0/16; };
    zone "example.com" {
        type master;
        file "/etc/bind/zones/internal/example.com.db";
    };
};

view "external" {
    match-clients { any; };
    zone "example.com" {
        type master;
        file "/etc/bind/zones/external/example.com.db";
    };
};
```

**Example usage and expected output:**

```bash
# Querying from an internal (10.0.0.0/8) client:
$ dig api.example.com +short
10.0.1.15

# Querying the same name, from an external client:
$ dig api.example.com +short
203.0.113.80
```

**Production usage example:** Organizations running self-hosted BIND for internal-plus-external DNS use exactly this `view`/`match-clients` pattern to serve internal service discovery records to VPN and office-network clients while keeping the public zone limited to genuinely externally reachable names — often maintaining two separate zone files (as shown) so an internal name never even appears in the externally served zone at all.

**Common errors:** BIND evaluates `view` clauses top-to-bottom and uses the first matching view — a common misconfiguration mistake is ordering an overly broad `match-clients { any; }` view *before* a more specific internal one, causing every client, internal or external, to match the wrong (usually external) view first.

### 5.2 Testing Which View a Given Vantage Point Sees

**Purpose:** Directly confirm which answer a specific network location actually receives, rather than assuming based on configuration alone.

**Syntax:**

```bash
dig <domain> @<resolver-ip> +short
```

**Example usage and expected output:**

```bash
# From inside the VPN:
$ dig internal-api.example.com @10.0.0.2 +short
10.0.1.15

# From a public network, querying the same authoritative infrastructure:
$ dig internal-api.example.com @203.0.113.1 +short
;; no answer — NXDOMAIN, name intentionally not published externally
```

**Production usage example:** When a team reports "the service works from the office but not remotely," running this exact comparison from both vantage points (or asking someone on each network to run it) is the fastest way to confirm whether the difference is expected split-horizon behavior — the correct fix might be "use the VPN" rather than any DNS misconfiguration at all.

**Common errors:** Testing only from one vantage point and concluding "DNS is broken" is the most common mistake here — split-horizon DNS is working *as designed* if internal names correctly fail to resolve externally; the actual bug (if any) is usually a client being on the wrong network for what it's trying to reach, or a genuine misconfiguration of which view a specific network segment is routed to.

## 6. Production Usage Notes

- **Split-horizon setups should keep the internal and external zone contents intentionally different, not just differently valued** — an internal-only view can and should omit names that have no legitimate external purpose entirely (returning `NXDOMAIN` for them externally), rather than merely pointing them at a different but still-resolvable external answer, to avoid unnecessarily disclosing internal naming conventions.
- **Managed cloud "private zone" features ([§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md)) are the modern, strongly preferred way to implement this pattern** for most infrastructure teams, since they bind the "internal" view explicitly to a specific VPC/VNet's network identity rather than relying on IP-range matching that can be fragile across VPNs, peering, and multi-region topologies.
- **Consistency between views matters for anything that depends on predictable behavior across environments** — a staging environment that resolves a name differently than production's internal view (due to an inconsistent split-horizon configuration) is a subtle, hard-to-catch source of "works in staging, breaks in prod" incidents.

## 7. Security Considerations

- **Split-horizon is not, by itself, an access-control mechanism** — a name being invisible on the external view does not make the underlying resource unreachable if network routing or a misconfigured firewall still permits external access to its IP directly; DNS visibility and network reachability are separate controls that must both be correctly configured.
- **Relying on "security through DNS obscurity" (assuming internal names are safe because external users can't resolve them) is a weak posture on its own** — internal hostnames are frequently discoverable through other channels (certificate transparency logs for internal names issued with public CAs, misconfigured internal tools, employee mistakes) and should not be the sole barrier protecting sensitive internal services.
- **Misconfigured view-matching logic (as in the BIND ordering pitfall above) can accidentally expose internal-only records externally**, which is a genuine, checkable security regression worth including in any periodic external DNS audit alongside the zone-transfer checks from [§48](Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                 | Resolution Path                                                                                          |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| A service is reachable from the office/VPN but not from home       | Split-horizon DNS correctly serves an internal-only answer to internal clients and no answer (or a different one) externally | Confirm this is expected behavior; if remote access is required, connect via VPN or expose the service through an intentional external-facing path |
| An internal hostname unexpectedly resolves from outside the corporate network | View-matching misconfiguration (e.g., an overly broad rule matched before the internal-only rule) | Review view/match-order configuration; test explicitly from both internal and external vantage points     |
| Staging environment behaves differently from production for the same internal hostname | Split-horizon configuration differs (or is missing) between environments      | Audit and align internal/external view configuration and content across all environments                  |

## 9. Best Practices

- Prefer a cloud provider's native private-zone feature ([§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md)) over hand-rolled IP-based view matching wherever the workload already runs in that cloud, since it ties view selection to verified network identity (VPC/VNet association) rather than potentially spoofable or fragile IP-range matching.
- Keep internal-only names entirely absent from the external view (returning `NXDOMAIN`) rather than resolvable-but-unreachable, to minimize unnecessary disclosure of internal naming conventions to anyone probing from outside.
- Test split-horizon behavior explicitly from every vantage point that matters (office network, VPN, each cloud region/VPC, and the public Internet) as part of any change to DNS view configuration, rather than relying on a single test location.

## 10. Common Anti-Patterns / Mistakes

- **Assuming split-horizon DNS alone provides meaningful access control for a sensitive internal service.** It hides a name from a casual external query, but does nothing to prevent access if the underlying IP is otherwise reachable — network-level controls (firewalls, security groups) are still required.
- **Ordering view-matching rules incorrectly (in BIND or equivalent) so a broad, catch-all rule shadows a more specific internal rule.** This silently serves the wrong view to a subset of clients, often undetected until an external user reports seeing data that should have been internal-only.
- **Diagnosing "it doesn't work remotely" purely as a network problem without considering that split-horizon DNS may be correctly and intentionally returning a different or no answer at all** — wasting troubleshooting effort on the wrong layer.

## 11. Interview Questions

**🎯 Beginner:** _"What is split-horizon DNS, in plain terms?"_
**Model answer:** Split-horizon DNS means the same domain name can resolve to different answers depending on where the query is coming from — typically, clients inside a private corporate network or VPC get a private, internal IP address for a name, while clients outside that network get a different (often public-facing) answer, or no answer at all if the name shouldn't be externally visible.
_What the interviewer is probing for:_ Correctly grasping the "same name, different answer by vantage point" core concept.

**🎯 Intermediate:** _"A colleague says a service 'isn't in DNS' because they can't resolve it from their home laptop, even though it works fine for everyone in the office. What would you check first?"_
**Model answer:** Before assuming a real DNS misconfiguration, I'd check whether this is expected split-horizon behavior — the name may be intentionally served only on an internal view, resolvable only to clients on the office network or VPN. I'd test resolving the same name from both an internal vantage point (confirming it resolves as expected there) and the external vantage point (confirming what, if anything, is returned there) to establish whether the behavior is by design. If it is by design, the actual fix isn't a DNS change at all — it's connecting via VPN or, if remote access is a genuine new requirement, deliberately exposing the service through an intentional external-facing path.
_What the interviewer is probing for:_ Whether the candidate recognizes split-horizon as a common, non-bug explanation before jumping to "DNS is broken."

**🎯 Senior:** _"What are the risks of relying on split-horizon DNS as a security boundary for an internal service, and how would you actually secure that service?"_
**Model answer:** Split-horizon DNS only controls whether a name *resolves* differently by vantage point — it says nothing about whether the underlying IP address is actually reachable from outside. If the service's IP is routable and its port is open to external traffic (a misconfigured security group, a NAT rule, or simply a public IP with no filtering), an attacker who discovers or guesses the IP directly bypasses DNS entirely. Internal hostnames can also leak through channels split-horizon doesn't control, like certificate transparency logs if a public CA issued a certificate for the internal name. I'd secure the service with actual network-layer controls — security groups/NACLs restricting the port to the internal network's IP ranges, and ideally placing the service on a private subnet with no public IP or route to the Internet at all — treating split-horizon DNS purely as a convenience for internal service discovery, never as the access-control mechanism itself.
_What the interviewer is probing for:_ Clear separation between DNS-layer visibility and network-layer access control, and awareness that "security through DNS obscurity" is not real security.

**🎯 Architect:** _"You're designing DNS for a multi-region, multi-VPC organization where each region needs to resolve shared internal service names to its own regionally local instance. How would you architect this using split-horizon concepts?"_
**Model answer:** I'd use a cloud provider's private-zone feature associated per-VPC/VNet rather than IP-range-based view matching, since that scales more reliably across regions and avoids the fragility of maintaining IP-range lists as the network topology grows or peering relationships change. I'd structure it as one shared internal zone name (e.g., `svc.internal.example.com`) with the *same relative names* resolving to different, regionally local records depending on which VPC's private zone is answering — associating each region's private zone with only that region's VPC(s), so a client in `us-east` naturally resolves the name to the `us-east` instance while a client in `eu-west` resolves the identically-named record to the `eu-west` instance. This gives every region's workloads a consistent naming convention while automatically routing each to the nearest instance, without needing per-region hostnames or application-level region-detection logic. I'd keep this fully separate from the organization's externally facing DNS view, and pair it with genuine network segmentation (private subnets, security groups) rather than treating the private-zone association itself as an access-control boundary.
_What the interviewer is probing for:_ Ability to design a real multi-region split-horizon architecture using modern cloud-native primitives, while still correctly separating DNS-layer convenience from actual network security.

## 12. Common Misconceptions

1. **"Split-horizon DNS and DNS-based load balancing ([§52](Section-52-Part6-DNS-Based-Load-Balancing-and-Failover-Patterns.md)) are the same thing."** Split-horizon serves different answers by *who's asking* (network origin); DNS-based load balancing serves different (or rotating) answers to distribute traffic across multiple healthy endpoints — they can be combined but solve different problems.
2. **"An internal-only DNS name is inherently secure because outsiders can't look it up."** Name visibility and network reachability are separate; an internal name that's unresolvable externally provides no protection if the underlying IP is still reachable through some other path.
3. **"Split-horizon DNS requires two entirely separate DNS server products or vendors."** It's commonly implemented within a single DNS server's configuration (BIND's `view` statement) or as a single managed cloud provider's private + public zone pairing — no separate vendor relationship is required.
4. **"If a service works from the office, DNS is fine everywhere."** Split-horizon means DNS correctness is inherently vantage-point-dependent — "DNS is fine" has to be qualified by *which* network you tested it from.

## 13. 🔑 Key Takeaways

- Split-horizon (split-view) DNS serves different answers for the same domain name depending on the querier's network origin, most often distinguishing internal/private clients from external/public ones.
- View selection is typically enforced by network topology (which resolver a client can even reach, or IP-range matching) rather than by the DNS protocol inspecting query content.
- Cloud providers implement this pattern natively as "private hosted zones" tied to a specific VPC/VNet, which is generally more robust than hand-rolled IP-range matching on self-managed nameservers.
- Split-horizon DNS is a convenience/routing mechanism, not a security control — the underlying resource still needs real network-layer access controls regardless of which DNS view can see its name.
- A common, non-bug troubleshooting pattern is "works on the office network/VPN, not from home" — this is often correct, intentional split-horizon behavior, not a misconfiguration.

## 14. Related Concepts & What's Next

[§44](Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)'s zone concept and [§46](Section-46-Part6-Recursive-vs-Iterative-Resolution-Resolvers-and-Root-TLD-Authoritative-Servers.md)'s resolver model underlie how split-horizon is actually implemented — different views are, structurally, different zones or zone contents served based on which resolver/network path a query travels. [§45](Section-45-Part6-DNS-Record-Types-A-AAAA-CNAME-MX-TXT-NS-SOA-SRV-PTR.md)'s ordinary record types are exactly what differs between views; split-horizon doesn't introduce new record types, only new answer-selection logic. [§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md) is the direct continuation of this section, showing how AWS Route 53, Azure DNS, and GCP Cloud DNS each implement split-horizon as a managed, VPC-associated private-zone feature.

**Next Section:** [§51](Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md) — `Section-51-Part6-DNS-in-Cloud-Environments-Route-53-Azure-DNS-Cloud-DNS-Conceptual.md`
