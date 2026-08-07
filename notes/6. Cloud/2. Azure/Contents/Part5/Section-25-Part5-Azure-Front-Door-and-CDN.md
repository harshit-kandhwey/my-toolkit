# Section 25 — Azure Front Door & CDN

## 1. Definition

**Plain language:** Azure Front Door is a global entry point for your web application — it sits in front of your app across multiple regions worldwide, routing each user to the closest or healthiest region, while also caching content near users and protecting against attacks. Azure CDN is focused more narrowly on caching and delivering static content (images, videos, scripts) from locations physically close to users, wherever they are in the world.

**Precise definition:** **Azure Front Door** is a global, Layer 7 application delivery service operating at the edge of Microsoft's global network (the Points of Presence introduced in [Section 3](../Part1/Section-03-Part1-Azure-Global-Infrastructure.md).3.5), providing global HTTP/HTTPS load balancing across multiple backend regions/origins, URL-based routing, SSL offload, an integrated WAF, and content caching. **Azure CDN (Content Delivery Network)** is a globally distributed network of edge servers that cache and serve content close to end users, reducing latency and origin server load for content that doesn't need to be fetched fresh from the origin on every request.

## 2. Why It Exists / Problem It Solves

The load-balancing mechanisms covered in [Section 24](./Section-24-Part5-Load-Balancer-vs-Application-Gateway.md) (Load Balancer, Application Gateway) operate **within a single region** — they distribute traffic across backend instances in that region, but do nothing to address a user in Australia experiencing high latency reaching an application whose only deployment is in the US, nor do they provide any mechanism for automatic failover if that entire US region becomes unavailable. Front Door and CDN exist to solve problems at a genuinely global scale: routing each user to the nearest or best-performing regional deployment (dramatically reducing latency for geographically distributed user bases), providing automatic failover across regions if one becomes unhealthy, and caching content at edge locations physically close to users so that repeated requests for the same content don't need to travel all the way back to a potentially distant origin server every time.

## 3. Azure Front Door

### 3.1 Global Load Balancing and Failover

Front Door continuously health-probes each configured backend/origin (which could be App Service deployments, Application Gateways, or other endpoints in different regions) and routes incoming user traffic to a healthy backend based on configurable routing methods — including **latency-based routing** (directing users to the backend that will provide the lowest latency for them specifically, typically the geographically nearest healthy region) and **priority-based routing** (directing all traffic to a primary region, only failing over to a secondary region if the primary becomes unhealthy, useful for active-passive DR architectures covered further in Part 12).

### 3.2 URL-Based Routing and Rules Engine

Similar in concept to Application Gateway's path-based routing ([Section 24](./Section-24-Part5-Load-Balancer-vs-Application-Gateway.md).4.1) but applied at the global edge layer rather than within a single region, Front Door can route different URL paths to entirely different backend origins — useful for architectures where, for example, `/api/*` is served by one set of regional backends while `/static/*` is served by a different, CDN-optimized origin. Front Door's **Rules Engine** allows more sophisticated conditional logic (based on request headers, geographic origin of the request, device type, and other signals) to customize routing and response behavior beyond simple path matching.

### 3.3 Caching

Front Door includes built-in content caching at Microsoft's global edge network, similar in principle to CDN's core function ([Section 25](./Section-25-Part5-Azure-Front-Door-and-CDN.md).4) — for content that's cacheable (static assets, or dynamic content explicitly marked cacheable via appropriate HTTP cache-control headers), Front Door can serve subsequent requests directly from the edge cache without needing to contact the origin backend at all, reducing both latency for the user and load on the origin.

### 3.4 Integrated WAF

Like Application Gateway, Front Door offers an integrated Web Application Firewall, but applied at the global edge — meaning malicious traffic can be filtered and blocked at the edge, geographically close to its source, before it ever reaches (and consumes capacity on) the regional backend infrastructure at all — an important distinction from a regional WAF (like Application Gateway's), which only filters traffic after it has already traveled all the way to that specific region.

## 4. Azure CDN

### 4.1 Core Caching Function

CDN's primary purpose is caching content (images, videos, JavaScript/CSS files, downloadable files, and other static or infrequently-changing content) at edge locations distributed globally, so that a user's request for that content is served from a nearby edge cache rather than requiring a round-trip all the way to the origin server, which might be geographically distant — this directly improves perceived load time for end users and reduces bandwidth/load on the origin.

### 4.2 Cache Behavior and TTL

Cached content has a **Time-To-Live (TTL)** — the duration for which the edge cache considers its cached copy valid before it must re-fetch from the origin — TTL can be controlled via standard HTTP cache-control headers set by the origin, or overridden via CDN-specific caching rules; choosing appropriate TTL values is a deliberate trade-off between cache freshness (shorter TTL means changes to origin content propagate to users faster) and cache efficiency (longer TTL means more requests served from cache without hitting the origin, reducing origin load and improving average latency).

### 4.3 CDN vs. Front Door — Overlapping but Distinct

⚠️ Front Door and CDN have functionally overlapping capabilities (both provide edge caching and global content delivery), and Microsoft's specific product positioning and feature differentiation between them (including specific CDN product tiers/variants that have existed historically) has evolved over time — current official guidance should be checked on the currently recommended service for a given caching/global-delivery use case, since this is an area where Microsoft's own product lineup and recommendations have shifted, and older documentation or training material may reference a product structure that no longer precisely matches current offerings.

**General distinguishing principle (subject to the above caveat):** Front Door is positioned as a fuller **application delivery** solution (global load balancing across dynamic application backends, plus caching, plus WAF, plus rules engine) appropriate when the primary need is intelligently routing and protecting a dynamic, multi-region application. CDN is positioned more narrowly around **content caching and delivery** specifically, appropriate when the primary need is efficiently delivering largely static content globally, without necessarily needing the fuller application-routing and multi-origin failover capabilities Front Door provides.

## 5. Architecture Diagram

```
Global Users (Australia, US, Europe)
   │
   ▼
Azure Front Door (global edge, Points of Presence — Section 3.3.5)
   │  - Latency-based routing: sends each user to their nearest healthy region
   │  - WAF filtering at the edge, before traffic reaches any region
   │  - Edge caching for cacheable content
   │  - Path-based routing: /api/* vs /static/*
   │
   ├──▶ Region: Australia East   (App Service / Application Gateway + backend pool)
   ├──▶ Region: East US          (App Service / Application Gateway + backend pool)
   └──▶ Region: West Europe      (App Service / Application Gateway + backend pool)

If East US becomes unhealthy (fails Front Door's health probes):
   Front Door automatically stops routing traffic there,
   redirecting affected users to the next-best healthy region
```

## 6. Configuration & Hands-On Example

**Creating a Front Door profile with two backend origins (conceptual, abbreviated):**

```bash
az afd profile create \
  --resource-group rg-myapp-prod \
  --profile-name afd-webapp-global \
  --sku Standard_AzureFrontDoor

az afd endpoint create \
  --resource-group rg-myapp-prod \
  --profile-name afd-webapp-global \
  --endpoint-name afd-webapp-endpoint

az afd origin-group create \
  --resource-group rg-myapp-prod \
  --profile-name afd-webapp-global \
  --origin-group-name og-webapp \
  --probe-request-type GET \
  --probe-protocol Https \
  --probe-interval-in-seconds 30

az afd origin create \
  --resource-group rg-myapp-prod \
  --profile-name afd-webapp-global \
  --origin-group-name og-webapp \
  --origin-name origin-eastus \
  --host-name app-webapp-eastus.azurewebsites.net \
  --priority 1 --weight 1000

az afd origin create \
  --resource-group rg-myapp-prod \
  --profile-name afd-webapp-global \
  --origin-group-name og-webapp \
  --origin-name origin-westeurope \
  --host-name app-webapp-westeurope.azurewebsites.net \
  --priority 1 --weight 1000
```

- **Purpose:** Creates a Front Door profile, an endpoint (the public-facing Front Door URL), an origin group with a defined health probe, and two origins (App Service deployments in different regions) both at equal priority (`--priority 1`) and equal weight — implementing latency-based routing across both healthy regions, following the pattern shown in [Section 25](./Section-25-Part5-Azure-Front-Door-and-CDN.md).5's diagram.
- **Important arguments explained individually:**
  - `--priority` — origins with the same priority participate in latency-based load balancing among themselves; a different, lower-precedence priority value would instead be used for active-passive failover (only receiving traffic if higher-priority origins are unhealthy), directly implementing the priority-based routing method described in [Section 25](./Section-25-Part5-Azure-Front-Door-and-CDN.md).3.1.
  - `--probe-interval-in-seconds` — controls how frequently Front Door checks each origin's health; shorter intervals detect failures faster but increase probe traffic load on the origin, a tunable trade-off.
- ⚠️ Exact Front Door CLI command names, required sub-resources (routes, rule sets), and SKU naming have evolved as the product itself has evolved (including a notable architectural revision from "classic" Front Door to the current profile-based model) — verify current command syntax and resource model against official documentation before building a production configuration, since this is one of the more actively-evolving areas of Azure's networking service catalog.

## 7. Production & Enterprise Usage

Enterprises with a genuinely global user base deploy Front Door in front of multi-region application backends specifically to minimize latency for geographically distributed users and to provide automatic regional failover without requiring DNS-based failover mechanisms (which can suffer from client-side DNS caching delays), while using its edge WAF to filter malicious traffic before it ever reaches regional infrastructure. CDN (or Front Door's own caching capability) is layered in specifically for static asset delivery (images, videos, downloadable files, front-end application bundles) regardless of whether the broader application uses Front Door for its dynamic traffic routing as well. This global layer sits architecturally above everything covered in Sections 21-24 — Front Door routes to a region, and within that region, the VNet, NSG, Load Balancer, and Application Gateway concepts already covered handle the traffic from there.

## 8. Security Considerations

- Filtering malicious traffic at the global edge (via Front Door's WAF) before it reaches regional infrastructure reduces the attack surface and resource consumption burden on regional backends, compared to relying solely on a regional WAF (Application Gateway) that only sees traffic after it has already reached that specific region.
- Origins behind Front Door should ideally be configured to accept traffic **only** from Front Door itself (rather than remaining separately, directly internet-accessible), preventing attackers from bypassing Front Door's WAF and global protections entirely by targeting the regional origin's own public endpoint directly — a subtle but important security configuration detail, since an origin left directly publicly reachable undermines much of the protective value Front Door's edge WAF is meant to provide.

## 9. Performance Considerations

Latency-based routing's effectiveness depends on Front Door correctly estimating actual network latency between the requesting user and each candidate origin region — this is generally accurate and well-optimized by Microsoft's global network telemetry, but application design should still ensure that whichever region a user is routed to can independently serve their request correctly (e.g., session state or data must be either globally consistent/replicated across regions or the routing must be sufficiently sticky/consistent per user) — global routing introduces genuine data-consistency architecture considerations that a single-region deployment doesn't have to address.

## 10. Monitoring

Front Door provides access logs and WAF logs at the global edge layer, integrated with Azure Monitor (Part 10), giving visibility into traffic patterns, routing decisions, cache hit/miss ratios, and blocked malicious requests across the entire global footprint — valuable both for performance tuning (are users actually being routed to genuinely optimal regions?) and security monitoring (what traffic is being blocked, and from where?).

## 11. Troubleshooting

| Symptom                                                                                                | Likely Cause                                                                                                                             | Fix                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Users in a specific geography experience unexpectedly high latency despite Front Door being configured | Latency-based routing may be sending them to a suboptimal region due to origin health issues, or origin priority/weight misconfiguration | Review Front Door's origin health status and routing configuration; verify the expected origin is actually healthy and correctly prioritized/weighted                           |
| Attackers appear to be bypassing Front Door's WAF entirely                                             | Origin backend is still directly, separately internet-accessible, allowing traffic to reach it without passing through Front Door at all | Restrict the origin to accept traffic only from Front Door (e.g., via IP restrictions matching Front Door's published IP ranges, or a shared header-based validation mechanism) |
| Cached content isn't updating after an origin content change                                           | TTL hasn't yet expired, or cache-control headers are causing longer-than-expected caching                                                | Review and adjust TTL/cache-control configuration, or manually purge the cache if an immediate update is required                                                               |

## 12. Interview Questions — [Section 25](./Section-25-Part5-Azure-Front-Door-and-CDN.md)

### 🎯 Intermediate

**Q: How does Azure Front Door differ from a regional Load Balancer or Application Gateway?**

_Model answer:_ Load Balancer and Application Gateway both operate within a single region, distributing traffic across backend instances located there. Front Door operates at a global level, sitting in front of potentially multiple regional deployments (each of which might itself use Application Gateway or Load Balancer internally), routing each user to the best available region based on latency or priority, and providing automatic cross-region failover if an entire region becomes unhealthy — a capability neither Load Balancer nor Application Gateway can provide on their own, since they have no visibility or control beyond their own single region.

_What the interviewer is probing:_ understanding of the layered nature of Azure's traffic-distribution services — global (Front Door) sitting above regional (Application Gateway/Load Balancer) — rather than treating them as competing, interchangeable alternatives.

### 🎯 Senior/Architect

**Q: Design a globally available, resilient architecture for a web application serving users across North America, Europe, and Asia, with automatic failover if any single region fails.**

_Model answer:_ I'd deploy the application independently in at least three regions, one roughly matching each major user population (e.g., East US, West Europe, Southeast Asia), each region internally using an Application Gateway with WAF fronting an autoscaling VM Scale Set or App Service deployment, following the regional patterns covered in Sections 12, 13, and 24. Azure Front Door would sit above all three regional deployments as the single global entry point, using latency-based routing so each user is automatically directed to their nearest healthy region, with continuous health probing enabling automatic failover — if, say, the Southeast Asia region became unhealthy, Front Door would automatically redirect affected users to their next-best-latency healthy region (likely West Europe or East US, depending on actual measured latency) without requiring any manual intervention or DNS propagation delay. I'd ensure each regional origin is configured to accept traffic only from Front Door directly, preventing WAF bypass via direct regional access. For data consistency across regions, I'd need to decide whether the application requires globally consistent data (pointing toward a globally-distributed database like Cosmos DB, [Section 30](../Part6/Section-30-Part6-Cosmos-DB.md), with multi-region write support) or whether each region can operate against region-local data with acceptable eventual consistency — this data-architecture decision is at least as important as the traffic-routing design itself, since routing users to the nearest healthy region doesn't automatically solve the underlying data-consistency challenge of a truly multi-region-active application.

_What the interviewer is probing:_ whether the candidate can design a complete global architecture spanning multiple layers (global routing via Front Door, regional load balancing, and the often-overlooked data-consistency implications of true multi-region deployment) rather than only addressing the traffic-routing layer in isolation.

## 13. Common Misconceptions

- **"Front Door and a regional Application Gateway are competing, interchangeable alternatives."** False — they operate at different layers (global vs. regional) and are commonly used together, with Front Door routing to one of several regions, each of which may use Application Gateway internally.
- **"Deploying an application across multiple regions behind Front Door automatically solves data consistency."** False — Front Door solves traffic routing and failover; data consistency across regions is a separate, often significant architectural challenge that must be deliberately addressed (Part 12's HA/DR discussion, and Cosmos DB's multi-region capabilities, [Section 30](../Part6/Section-30-Part6-Cosmos-DB.md)).

## 14. Key Takeaways

- 🔑 Front Door and CDN operate at Microsoft's global edge network (Points of Presence, [Section 3](../Part1/Section-03-Part1-Azure-Global-Infrastructure.md).3.5), a layer above regional load-balancing mechanisms (Load Balancer, Application Gateway).
- 🔑 Front Door provides global HTTP/HTTPS load balancing (latency-based or priority-based), URL-based routing, edge WAF, and caching; CDN focuses more narrowly on caching and delivering largely static content globally.
- 🔑 Origins behind Front Door should be restricted to accept traffic only from Front Door itself, to avoid attackers bypassing the edge WAF by reaching the regional origin directly.
- 🔑 Global traffic routing (Front Door) and cross-region data consistency (a database/architecture-level concern) are separate problems that both must be deliberately addressed in a true multi-region-active architecture.

## 15. Related Concepts (Next Up)

[Section 26](./Section-26-Part5-VPN-Gateway-and-ExpressRoute.md) covers **VPN Gateway & ExpressRoute** — the mechanisms for connecting an Azure VNet to on-premises networks, extending the private connectivity concepts from VNet Peering ([Section 23](./Section-23-Part5-VNet-Peering-Service-Endpoints-Private-Link.md)) to hybrid cloud scenarios (the deployment model introduced conceptually in [Section 2](../Part1/Section-02-Part1-Cloud-Service-and-Deployment-Models.md).8), and forming the hub-side connectivity component of the hub-and-spoke topology referenced throughout this Part.
