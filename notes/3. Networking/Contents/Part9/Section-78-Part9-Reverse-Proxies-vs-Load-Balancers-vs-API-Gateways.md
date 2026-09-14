# Section 78 (Part 9): Reverse Proxies vs. Load Balancers vs. API Gateways

## 1. Definition

**Plain language:** These three things — a reverse proxy, a load balancer, and an API gateway — are often confused because a single piece of software (NGINX, Envoy) can implement all three at once. But they describe three different jobs: a reverse proxy sits in front of a server and forwards requests to it on behalf of clients; a load balancer specifically spreads requests across many servers; an API gateway adds a layer of API-specific concerns — authentication, rate limiting, request transformation — on top of routing. Many real deployments blend all three into one component, which is exactly why the distinction gets muddled.

**Precise definition:** A **reverse proxy** is any server that sits between clients and one or more backend servers, receiving requests on the backends' behalf and forwarding them, presenting a single external-facing identity regardless of how many backends exist behind it — a reverse proxy can front even a single backend server, purely for the benefits of centralizing TLS, caching, or request logging. A **load balancer** is a specific application of the reverse proxy pattern (when implemented at Layer 7) or a lower-level forwarder (when implemented at Layer 4, [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)) whose defining purpose is distributing traffic across *multiple* backend instances according to an algorithm ([§74](Section-74-Part9-Load-Balancing-Algorithms-Round-Robin-Least-Connections-Weighted-Hashing.md)) and health status ([§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md)) — every load balancer is functionally a reverse proxy, but not every reverse proxy is doing load balancing (a single-backend reverse proxy is not). An **API gateway** is a specialized reverse proxy purpose-built for API traffic that adds concerns beyond routing and distribution: authentication/authorization enforcement, request/response transformation, rate limiting per API consumer, API versioning, and often aggregating calls to multiple backend services into a single client-facing API surface.

> 💡 **Tip:** A useful test to place a given component: if its main job is "make many servers look like one," it's primarily a load balancer. If its main job is "enforce API-specific policy and shape the request/response for API consumers," it's primarily an API gateway. If it's just "sit in front of a server and forward on its behalf" with no distribution or API-specific logic, it's a plain reverse proxy. The same physical software can do all three at once, but the *purpose* being served in a given deployment is usually clear from context.

## 2. Why This Matters

- **These terms appear constantly in architecture diagrams and job descriptions, often used loosely or interchangeably**, and being unable to distinguish them makes it hard to understand what a given component in a real system actually does or why it was chosen.
- **Choosing the wrong category of tool for a given problem wastes effort.** Building custom per-consumer rate limiting and authentication logic into a plain load balancer (which isn't designed for that) when an API gateway product already provides it out of the box is a common, avoidable inefficiency.
- **The distinction determines where certain policies should logically live in an architecture.** API versioning and per-client rate limiting are API gateway concerns; backend health-aware traffic distribution is a load balancer concern; simple TLS centralization and static caching for a single service is a plain reverse proxy concern — misplacing these responsibilities creates confusing, hard-to-maintain architectures.
- **System design interviews frequently probe exactly this distinction** ("would you use a load balancer or an API gateway here, and why?"), and a fuzzy answer signals a fuzzy mental model of the whole request path.
- **Understanding the overlap (not just the differences) matters just as much** — knowing that NGINX, HAProxy, and Envoy ([§81](Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md)) can each function as any of these three depending on configuration avoids the trap of assuming they're mutually exclusive product categories.

## 3. Prerequisites and Dependencies

This section depends on the Layer 4/Layer 7 distinction from [§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md), since reverse proxies and API gateways are inherently Layer 7 components while pure load balancers can operate at either layer. It builds on the backend pool and algorithm concepts from [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md) and [§74](Section-74-Part9-Load-Balancing-Algorithms-Round-Robin-Least-Connections-Weighted-Hashing.md), and assumes basic HTTP request/response structure (Part 8, [§63](../Part8/Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) since API gateway responsibilities (authentication headers, request transformation) are described in HTTP terms throughout.

## 4. Architecture / Conceptual Diagram

```text
   PLAIN REVERSE PROXY              LOAD BALANCER                  API GATEWAY
   (single backend, no              (many backends, health-        (API-specific policy
    distribution needed)             aware distribution)             layer on top of routing)

   Client ──► Proxy ──► Backend     Client ──► LB ──┬──► Backend A  Client ──► Gateway
              (TLS termination,                     ├──► Backend B         │
               caching, logging                     └──► Backend C         ├─ authenticate
               centralized here,                                            ├─ rate-limit
               even for ONE                          Distributes by         │  per API key
               backend)                              algorithm (§74),       ├─ transform
                                                      health-checked (§75)  │  request/response
                                                                             ├─ aggregate calls
                                                                             │  to multiple
                                                                             │  backend services
                                                                             ▼
                                                                     ┌───────┬───────┬───────┐
                                                                     ▼       ▼       ▼       ▼
                                                                  Users   Orders  Inventory Payments
                                                                  Service Service Service   Service

   Reverse proxy = the broad         Load balancer = a reverse       API gateway = a reverse
   pattern of fronting a backend     proxy specialized for           proxy specialized for
   (or backends) on their behalf     distributing across MANY        API-consumer-facing
                                     backends by algorithm            policy and orchestration
```

- **Every load balancer and every API gateway is, structurally, a reverse proxy** — the categories are not mutually exclusive product types but describe increasing specialization of the same underlying pattern (accept a request on a backend's behalf, decide what to do with it, forward it).
- **An API gateway typically sits in front of load balancers, not instead of them** — in a real architecture, the API gateway routes to a specific backend *service*, and a load balancer (or the gateway's own internal load-balancing logic) then distributes across that service's actual instances.
- **A single software product frequently implements all three roles simultaneously** in different deployments — NGINX as a plain reverse proxy for a single legacy app, as a load balancer for a scaled-out API tier, and (with additional modules or configuration) approaching API gateway functionality, all using the same underlying engine.

## 5. Hands-On

### 5.1 A Plain Reverse Proxy (Single Backend, No Distribution)

**Purpose:** Show the simplest form of the pattern — fronting a single backend purely for the benefits of centralized TLS and logging, with no load distribution involved at all.

**Syntax:**

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/certs/legacy-app.crt;
    ssl_certificate_key /etc/nginx/certs/legacy-app.key;

    location / {
        proxy_pass http://10.0.5.20:8080;   # exactly one backend
        access_log /var/log/nginx/legacy-app-access.log;
    }
}
```

**Example usage and expected output:**

```bash
$ curl -sv https://legacy-app.internal/ 2>&1 | grep "HTTP/"
< HTTP/1.1 200 OK
```

- There is no `upstream` block with multiple `server` entries here — this is purely a reverse proxy in front of one backend, gaining TLS termination and centralized access logging without any load-distribution logic at all.

**Production usage example:** This exact pattern is extremely common for legacy applications that were never designed to run more than one instance, where a team still wants the operational benefits (centralized TLS, request logging, IP allow-listing) of a proxy layer in front of it.

**Common errors:** Teams sometimes assume any NGINX/HAProxy deployment is automatically "load balancing" simply because it's a reverse proxy — if there's only one backend defined, no distribution decision is actually happening, no matter what the surrounding infrastructure is called in documentation.

### 5.2 A Load Balancer (Multiple Backends, Health-Checked Distribution)

**Purpose:** Contrast directly with §5.1 by showing the same proxy pattern applied with a real backend pool, which is what actually makes it a load balancer.

**Syntax:**

```nginx
upstream app_pool {
    server 10.0.1.10:8080;
    server 10.0.1.11:8080;
    server 10.0.1.12:8080;
}

server {
    listen 443 ssl;
    location / {
        proxy_pass http://app_pool;
    }
}
```

**Example usage and expected output:**

```bash
$ for i in 1 2 3; do curl -s https://app.internal/health | jq -r .served_by; done
10.0.1.10
10.0.1.11
10.0.1.12
```

- The only structural difference from §5.1 is the `upstream` block with multiple `server` entries — the same reverse-proxy engine is now performing genuine load balancing because there's more than one backend to distribute across.

**Production usage example:** This is the standard configuration for any horizontally scaled service, and it's the pattern most people mean when they say "load balancer," even though the underlying software (NGINX here) is identical to the plain reverse proxy in §5.1.

**Common errors:** Adding a second backend to what was a single-backend reverse-proxy configuration, without also adding health checks ([§75](Section-75-Part9-Health-Checks-and-Failover-Behavior.md)), silently turns a previously reliable single-point setup into one where a failed backend now receives a share of traffic with no automatic removal — the "it was working fine before" instinct can mask that a real load-balancing concern (health awareness) was never actually configured.

### 5.3 An API Gateway Layer (Authentication and Rate Limiting on Top of Routing)

**Purpose:** Show API-gateway-specific policy — authentication and per-consumer rate limiting — layered on top of routing to multiple backend services, illustrating what goes beyond plain load balancing.

**Syntax:**

```nginx
# Simplified conceptual example — real API gateways (Kong, AWS API Gateway,
# Envoy with ext_authz) implement this far more robustly, but the core
# idea maps directly onto reverse-proxy configuration primitives.

limit_req_zone $http_x_api_key zone=api_consumer:10m rate=100r/m;

server {
    listen 443 ssl;

    location /api/users/ {
        auth_request /validate-api-key;
        limit_req zone=api_consumer burst=20;
        proxy_pass http://users_service;
    }

    location /api/orders/ {
        auth_request /validate-api-key;
        limit_req zone=api_consumer burst=20;
        proxy_pass http://orders_service;
    }

    location = /validate-api-key {
        internal;
        proxy_pass http://auth_service/validate;
    }
}
```

**Example usage and expected output:**

```bash
$ curl -s -H "X-API-Key: invalid" https://api.example.com/api/users/42
{"error": "invalid API key"}

$ curl -s -H "X-API-Key: valid-key-123" https://api.example.com/api/users/42
{"id": 42, "name": "Alice"}

$ for i in $(seq 1 150); do curl -s -o /dev/null -w "%{http_code}\n" \
    -H "X-API-Key: valid-key-123" https://api.example.com/api/users/42; done | sort | uniq -c
    100 200
     50 429
```

- Requests are validated against an API key *before* reaching any backend service (`auth_request`), and are rate-limited per API consumer (keyed on `X-API-Key`) independent of the backend's own capacity — both are policy decisions specific to managing API consumers, not decisions about which backend instance should handle a request.
- Note that routing here is by URL path to *entirely different backend services* (`users_service`, `orders_service`), not to different instances of the *same* service — this is the API-orchestration aspect that goes beyond what a load balancer alone does.

**Production usage example:** This composition of authentication, per-consumer rate limiting, and multi-service routing is exactly the value proposition of dedicated API gateway products (Kong, Amazon API Gateway, Apigee) — teams often start by bolting this logic onto an existing reverse proxy/load balancer as shown here, then migrate to a dedicated gateway product as API consumer management requirements grow more sophisticated.

**Common errors:** Implementing per-consumer rate limiting keyed on a client-supplied header (like `X-API-Key` here) without validating that header's authenticity first creates a bypass — a request with a fabricated, never-issued key value simply gets its own independent rate-limit bucket, effectively sidestepping the intended limit entirely unless authentication is enforced strictly before the rate-limit check.

## 6. Production Usage Notes

- **Real architectures typically layer these concepts, not choose one exclusively** — a public API gateway routes to internal services, each of which sits behind its own internal load balancer distributing across that service's actual instances, which in turn might be a plain reverse proxy in front of a single instance during early-stage development.
- **API gateways introduce a meaningful additional hop and processing cost** (authentication checks, transformation logic) compared to a plain load balancer, which is a deliberate trade-off for the API-management capability gained — reaching for a full API gateway for purely internal, trusted service-to-service traffic that needs none of that policy is often unnecessary overhead.
- **The same software product (NGINX, Envoy, HAProxy) genuinely spans all three roles** depending on configuration, which is why job postings and documentation sometimes use the terms loosely — the distinguishing factor is always the configured *purpose* and *feature set in use*, not the underlying binary.

## 7. Security Considerations

- **API gateways are a natural, centralized enforcement point for authentication and authorization**, meaning a misconfigured or bypassed gateway (traffic reaching a backend service directly, skipping the gateway) can expose backend services with no authentication at all if those services assumed the gateway would always be the sole entry point — backend services should still validate authentication independently wherever the security model can afford it, rather than trusting network topology alone.
- **Rate limiting keyed on client-supplied, unauthenticated data is trivially bypassable**, as shown in §5.3's Common Errors — any per-consumer policy enforcement should be anchored to a value the gateway itself has already validated (an authenticated API key, a verified JWT claim), not raw client input.
- **A plain reverse proxy centralizing TLS for a single legacy backend is itself a security improvement** over exposing that backend directly, even with no load-balancing or API-gateway features involved at all — the security benefit of a reverse proxy layer doesn't require it to also be doing distribution or policy enforcement.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                                     | Resolution Path                                                                                                    |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| "Load balancer" only ever routes to one backend, no distribution observed | The component is actually functioning as a plain reverse proxy — only one backend is configured      | Confirm whether multiple backend instances actually exist and are registered; a single-backend setup isn't load balancing regardless of naming |
| API rate limits can seemingly be bypassed by changing a request header | Rate limiting is keyed on unauthenticated, client-controlled data rather than a validated identity   | Anchor rate-limit keys to authenticated identity (validated API key/token), enforced before the rate-limit check     |
| Backend service receives unauthenticated requests despite an API gateway in front | Backend is directly reachable, bypassing the gateway entirely (misconfigured network path/security group) | Restrict backend reachability so the gateway is the only viable path in; add independent backend-side auth as defense in depth |
| Confusion in an architecture review about what a given component actually does | Ambiguous terminology — "the load balancer" is actually performing API-gateway-like policy, or vice versa | Clarify the actual configured responsibilities (routing? distribution? auth/rate-limit policy?) rather than relying on the component's label |

## 9. Best Practices

- Name and document components by what they actually do (route to one backend, distribute across many, or enforce API-consumer policy), not just by the product name, since the same product can serve any of the three roles.
- Reach for a dedicated API gateway product only once API-consumer management requirements (authentication, per-consumer rate limiting, versioning, request transformation) genuinely exist — don't add that layer of complexity to purely internal, trusted service-to-service traffic that doesn't need it.
- Enforce backend-side authentication as defense in depth even behind an API gateway, rather than relying solely on network topology to guarantee the gateway is the only path in.

## 10. Common Anti-Patterns / Mistakes

- **Calling every reverse proxy a "load balancer" regardless of whether it actually distributes across multiple backends.** This creates confusion in architecture discussions and can mask the fact that a supposedly load-balanced service actually has a single point of failure.
- **Building bespoke authentication and per-consumer rate-limiting logic into a plain load balancer configuration instead of adopting a dedicated API gateway once that complexity is warranted.** This tends to produce a fragile, hard-to-maintain configuration reimplementing what mature gateway products already solve robustly.
- **Trusting network topology alone (gateway is "the only path in") without backend-side authentication as a backstop.** A single misconfigured security group or firewall rule then fully exposes an unauthenticated backend.

## 11. Interview Questions

**🎯 Beginner:** _"Is a load balancer the same thing as a reverse proxy?"_
**Model answer:** Not exactly — every load balancer is a kind of reverse proxy, but not every reverse proxy is a load balancer. A reverse proxy is any server that sits in front of a backend (or backends) and forwards requests on their behalf; a load balancer is specifically a reverse proxy whose job is to distribute traffic across multiple backend instances. A reverse proxy fronting just one backend server — purely for TLS termination or logging, say — isn't doing any load balancing at all.
_What the interviewer is probing for:_ Whether the candidate understands the terms as a specialization relationship rather than as interchangeable synonyms.

**🎯 Intermediate:** _"What does an API gateway add on top of what a plain load balancer already does?"_
**Model answer:** A load balancer's core job is distributing traffic across multiple instances of the same backend service, using an algorithm and health checks. An API gateway adds a layer of API-consumer-specific policy on top of routing: authenticating and authorizing each request, enforcing per-consumer rate limits, transforming requests or responses, handling API versioning, and often routing to and aggregating calls across multiple *different* backend services to present a unified API surface to consumers. A load balancer generally doesn't know or care who the client is beyond basic connection info; an API gateway is built specifically around managing API consumers as first-class concepts.
_What the interviewer is probing for:_ Clear articulation of the added responsibilities, not just a vague "gateways do more stuff" answer.

**🎯 Senior:** _"A team implemented API-key-based rate limiting directly in their load balancer configuration, keyed on a client-supplied header. A customer discovered they could bypass their rate limit by simply changing that header value on each request. What went wrong, and how do you fix it?"_
**Model answer:** The rate limit was keyed on a value the client fully controls and that was never authenticated — from the load balancer's perspective, a different header value is indistinguishable from a genuinely different customer, so each fabricated value gets its own fresh rate-limit bucket, trivially defeating the limit. The fix is to anchor the rate-limit key to something the system has actually validated — for instance, only apply the rate limit after confirming the API key is a real, issued key (via an authentication check), and key the limit on the *validated* customer identity associated with that key, not the raw header string itself. This is exactly the kind of policy enforcement a dedicated API gateway typically handles more robustly out of the box, since authentication and rate limiting are designed to work together rather than being bolted on independently.
_What the interviewer is probing for:_ Recognition that rate limiting must be anchored to authenticated identity, and the ability to trace a specific bypass back to its root configuration mistake.

**🎯 Architect:** _"You're designing the ingress layer for a platform exposing APIs to external third-party developers, while also running dozens of internal microservices that only talk to each other. Would you use the same component for both, and how would you structure the layers?"_
**Model answer:** I would not use the same component configured the same way for both, even if the underlying software could technically do it. For external third-party API traffic, I'd put a dedicated API gateway at the edge — handling API key or OAuth-based authentication, per-consumer rate limiting, request/response transformation, and versioning, since external developers need a stable, well-managed, policy-enforced contract that internal traffic doesn't require. That gateway routes to internal services, each of which sits behind its own internal load balancer distributing across that service's actual instances, using health checks and an algorithm suited to that service's traffic pattern — no API-key authentication or per-consumer rate limiting needed there, since internal service-to-service calls operate under a different trust model (mTLS or network-level trust, potentially a service mesh, [§113](../Part13/Section-113-Part13-Service-Mesh-Networking-Concepts-Sidecar-Proxies-mTLS.md)). Structuring it this way keeps the heavier, policy-laden API gateway logic scoped only to the traffic that actually needs it, while internal traffic flows through lighter-weight, lower-overhead load balancing — collapsing both into one uniform gateway layer would either over-burden internal traffic with unnecessary policy overhead or under-protect external traffic by treating it like a trusted internal caller.
_What the interviewer is probing for:_ The ability to design layered ingress that matches each traffic type's actual trust model and requirements, rather than defaulting to a single uniform component for an entire platform.

## 12. Common Misconceptions

1. **"Load balancer," "reverse proxy," and "API gateway" are three separate, mutually exclusive product categories.** They describe increasing specialization of the same underlying pattern, and the same software frequently implements all three depending on configuration.
2. **"A reverse proxy always implies load balancing is happening."** A reverse proxy in front of a single backend provides real value (TLS centralization, logging) with no distribution decision involved at all.
3. **"An API gateway replaces the need for load balancers behind it."** In practice, an API gateway typically routes to backend *services*, each of which is still fronted by its own load balancer distributing across that service's actual instances — the gateway and the load balancer usually coexist at different points in the request path.
4. **"Rate limiting at the gateway is inherently secure regardless of what it's keyed on."** Rate limiting keyed on unauthenticated, client-controlled data is trivially bypassable; it must be anchored to a value the gateway has already validated.

## 13. 🔑 Key Takeaways

- A reverse proxy is the general pattern (fronting a backend on its behalf); a load balancer is a reverse proxy specialized for distributing across multiple backend instances; an API gateway is a reverse proxy specialized for API-consumer policy (auth, rate limiting, transformation, multi-service routing).
- These are not mutually exclusive categories — the same software product frequently spans all three roles depending on configuration and deployment context.
- Real architectures typically layer these: an API gateway at the edge routing to internal services, each fronted by its own load balancer.
- Rate limiting and authentication policy must be anchored to validated, authenticated identity — never to raw, client-controlled input — or they're trivially bypassable.
- Choosing the right layer of specialization for a given traffic type (external API consumers vs. internal trusted services) avoids both unnecessary overhead and inadequate protection.

## 14. Related Concepts & What's Next

[§73](Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md) underlies why reverse proxies and API gateways are inherently Layer 7 components. [§111](../Part13/Section-111-Part13-The-Kubernetes-Networking-Model-Pod-to-Pod-Service-and-Ingress-Concepts.md) and [§113](../Part13/Section-113-Part13-Service-Mesh-Networking-Concepts-Sidecar-Proxies-mTLS.md) extend this layered pattern into the Kubernetes-native Ingress and service mesh sidecar-proxy models, respectively, which are direct applications of the reverse proxy/load balancer distinction drawn here. [§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md) moves the discussion up a level, from single-region traffic distribution to distributing traffic across entire regions or data centers.

**Next Section:** [§79](Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md) — `Section-79-Part9-Global-Server-Load-Balancing-GSLB-and-Anycast.md`
