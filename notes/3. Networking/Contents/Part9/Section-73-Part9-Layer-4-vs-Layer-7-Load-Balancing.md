# Section 73 (Part 9): Layer 4 vs. Layer 7 Load Balancing

## 1. Definition

**Plain language:** A Layer 4 load balancer makes its routing decision by looking only at IP addresses and ports — it forwards packets without caring what's inside them. A Layer 7 load balancer actually reads the HTTP request itself — the path, the headers, the host name — and can make much smarter, content-aware routing decisions because of it. That extra visibility costs more CPU and adds a little more latency, which is the fundamental trade-off between the two.

**Precise definition:** A **Layer 4 (L4) load balancer** operates at the transport layer ([§8](../Part2/Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md)), making forwarding decisions based solely on source/destination IP address and port and the transport protocol (TCP/UDP), without parsing or understanding the application-layer payload. It typically operates as a fast, largely stateless (or lightly stateful, tracking only connection tuples) packet/connection forwarder. A **Layer 7 (L7) load balancer** operates at the application layer, terminating the client's connection, fully parsing the application protocol (almost always HTTP/HTTPS in practice), and making routing decisions based on request content — URL path, HTTP method, headers, cookies, or the request body — before establishing a separate connection to the chosen backend. Because an L7 load balancer must terminate and re-establish connections and parse application data, it is inherently a **proxy**, whereas an L4 load balancer can often operate as a lower-overhead **forwarder** that never fully terminates the connection.

> 💡 **Tip:** A useful shorthand: if the routing decision could be made from a `tcpdump -XX` hex dump without decrypting or parsing anything past the TCP header, it's an L4 decision. If it requires reading the actual HTTP request line, headers, or body, it's an L7 decision — and if the traffic is TLS-encrypted, an L7 load balancer necessarily has to terminate that TLS connection first to see any of it ([§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md)).

## 2. Why This Matters

- **The choice determines what routing logic is even possible.** Path-based routing ("/api/* goes to the API service, /* goes to the web service"), host-based routing (multiple domains on one load balancer), and cookie-based session persistence ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) are all L7-only capabilities — an L4 load balancer structurally cannot see the information needed to make those decisions.
- **Performance and cost trade-offs are real and measurable.** L4 load balancing generally has lower latency and higher raw throughput per instance because it avoids full protocol parsing and TLS termination overhead; this is why extremely high-throughput or non-HTTP workloads (raw TCP services, UDP-based protocols, gaming servers) commonly use L4 load balancing even when L7 features would be nice to have.
- **Protocol support differs fundamentally.** L4 load balancers are protocol-agnostic in a real sense — they'll happily balance MySQL connections, arbitrary TCP services, or UDP traffic (like DNS or QUIC) that an HTTP-aware L7 load balancer has no native understanding of at all.
- **Cloud load balancer product lines are explicitly split along this line.** AWS offers a Network Load Balancer (L4) and an Application Load Balancer (L7) as genuinely distinct products with different capabilities and pricing ([§80](Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md)); the same L4/L7 split recurs across Azure and GCP's load balancer offerings, so this distinction is directly load-bearing when choosing a managed service, not just theoretical.
- **It's one of the most commonly tested distinctions in networking and cloud interviews**, precisely because it connects OSI-layer theory (Part 2) to a concrete, practical architectural decision.

## 3. Prerequisites and Dependencies

This section depends directly on [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md) for the general concept of a backend pool and health-checked routing, and on the OSI Layer 3/4/7 vocabulary from [§8](../Part2/Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md). A working understanding of the TCP three-way handshake and connection lifecycle (Part 7, [§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)-[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) is assumed for the "termination vs. forwarding" distinction drawn below, and basic HTTP request structure (Part 8, [§63](../Part8/Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) is assumed for the Layer 7 routing examples. [§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md) depends on this section, since TLS termination is only possible at a load balancer that has already terminated the underlying connection — an inherently L7-adjacent (or at minimum, proxy-mode) capability.

## 4. Architecture / Conceptual Diagram

```text
   LAYER 4 LOAD BALANCING                    LAYER 7 LOAD BALANCING
   (sees only IP + port)                     (sees full HTTP request)

   Client ──TCP SYN──► LB ──TCP SYN──► Backend    Client ──TCP + TLS──► LB
           (connection forwarded/NAT'd,                    │
            client's own TCP session                       │ LB terminates TLS,
            effectively continues to                        │ parses HTTP request:
            the backend — LB doesn't                        │   GET /api/orders
            re-terminate it)                                │   Host: api.example.com
                                                              │   Cookie: session=abc
   Decision inputs:                                          ▼
     - source IP : port                          ┌─────────────────────┐
     - destination IP : port                     │ Routing decision on: │
     - protocol (TCP/UDP)                        │  - URL path          │
                                                   │  - Host header       │
   Cannot see:                                    │  - Cookies           │
     - HTTP path, headers, cookies                │  - HTTP method       │
     - TLS contents (unless passthrough)          └──────────┬───────────┘
                                                               │
   Backend receives the ORIGINAL                     LB opens a NEW,
   connection semantics largely intact               separate connection
                                                       to the chosen backend
                                                       (re-encrypts if needed)

   Faster, lower overhead,                       Slower per-connection,
   protocol-agnostic (any TCP/UDP)                but far richer routing
                                                   and HTTP-native features
```

- An L4 load balancer's forwarding is often closer to Network Address Translation than to a true proxy — many implementations preserve the original TCP segment largely as-is, meaning the backend can even see the client's real source IP directly in some modes (like AWS NLB's default behavior), without needing an `X-Forwarded-For` header at all.
- An L7 load balancer necessarily creates **two separate TCP connections** for every client request — client-to-LB and LB-to-backend — because it must fully receive and parse the client's request before it can even know which backend to send it to.
- Some products (and software like Envoy and HAProxy) support **both modes simultaneously** on different listeners, and some support a hybrid "L4 passthrough with SNI-based routing" mode that inspects only the unencrypted TLS handshake's SNI field to route without full decryption — a middle ground covered further in [§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md).

## 5. Hands-On

### 5.1 Layer 7 Path-Based Routing With NGINX

**Purpose:** Demonstrate routing decisions that are only possible because the load balancer can read the HTTP request path — something structurally impossible for a pure L4 device.

**Syntax:**

```nginx
upstream api_backend {
    server 10.0.2.10:8080;
}
upstream web_backend {
    server 10.0.3.10:8080;
}

server {
    listen 80;

    location /api/ {
        proxy_pass http://api_backend;
    }

    location / {
        proxy_pass http://web_backend;
    }
}
```

**Example usage and expected output:**

```bash
$ curl -s http://lb.internal/api/orders
{"backend": "api", "orders": []}

$ curl -s http://lb.internal/
<html>...served by web_backend...</html>
```

- The same load balancer, same listening port, routes to two entirely different backend pools purely based on the URL path — this is impossible for an L4 load balancer, which has no visibility into the path at all and could only route by destination IP/port.

**Production usage example:** Path-based routing like this is the standard pattern for consolidating multiple microservices behind a single public hostname (`example.com/api/*` vs. `example.com/*`), avoiding the need for separate DNS names, separate TLS certificates, or separate public load balancers per service.

**Common errors:** Location block ordering and specificity in NGINX matter — a broad `location /` block placed before a more specific `location /api/` block, combined with certain regex-based location matching rules, can accidentally shadow the intended route; testing with `curl -v` against each expected path after any change is the reliable way to catch this.

### 5.2 Layer 4 TCP Forwarding With HAProxy

**Purpose:** Show a minimal Layer 4 configuration that forwards raw TCP connections without any HTTP awareness, appropriate for a non-HTTP protocol like a raw TCP service or database.

**Syntax:**

```
frontend tcp_front
    bind *:5432
    mode tcp
    default_backend postgres_pool

backend postgres_pool
    mode tcp
    balance leastconn
    server pg1 10.0.4.10:5432 check
    server pg2 10.0.4.11:5432 check
```

**Example usage and expected output:**

```bash
$ psql -h lb.internal -p 5432 -U app_user -d app_db -c "SELECT 1;"
 ?column?
----------
        1
(1 row)
```

- `mode tcp` explicitly tells HAProxy to operate at Layer 4 — it forwards the raw PostgreSQL wire protocol without attempting to parse it as HTTP, which would fail entirely since PostgreSQL's protocol isn't HTTP at all.
- This same `mode tcp` configuration works unmodified for any TCP-based service — Redis, MySQL, a custom TCP protocol — because L4 forwarding is inherently protocol-agnostic.

**Production usage example:** Database connection load balancing (particularly across read replicas) is a canonical use case for L4 load balancing — the protocol isn't HTTP, and the routing decision needed (which replica to send this connection to) doesn't require any application-layer awareness.

**Common errors:** Using `mode http` (or an HTTP-aware load balancer) against a non-HTTP TCP service like PostgreSQL will fail outright — the load balancer will attempt to parse the first bytes of the connection as an HTTP request line and reject or mishandle traffic that doesn't look like one; matching `mode` to the actual protocol being carried is not optional.

## 6. Production Usage Notes

- **L7 load balancing costs more, in both infrastructure terms and cloud pricing terms**, because it requires full connection termination, TLS handling, and protocol parsing per request rather than per connection — this is reflected directly in cloud pricing models where L7 products (ALB, Application Gateway) typically bill per processed request/LCU in addition to data volume, while L4 products (NLB) bill closer to pure data-volume terms.
- **A single architecture commonly uses both layers together**, not one or the other — an L4 load balancer distributing traffic across a fleet of L7 load balancers (or an L7 load balancer/API gateway) is a common pattern for extremely high connection-rate ingress that still needs eventual HTTP-aware routing.
- **Preserving the real client IP is a bigger operational concern at L7 than L4.** Because an L7 load balancer opens a brand-new connection to the backend, the backend sees the load balancer's IP as the "source" unless the load balancer explicitly forwards the original client IP via a header (`X-Forwarded-For`) or the Proxy Protocol; L4 load balancers frequently preserve the original source IP more naturally depending on their forwarding mode.

## 7. Security Considerations

- An L7 load balancer's ability to fully parse HTTP requests is precisely what makes it a natural enforcement point for WAF rules ([§89](../Part10/Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md)), request-size limits, and header validation — none of which an L4 load balancer can meaningfully enforce since it never sees the request content.
- L4 load balancing in TLS-passthrough mode leaves the load balancer blind to the encrypted payload entirely, which means it cannot detect or block a malicious HTTP request hidden inside an otherwise-permitted encrypted connection — that inspection responsibility shifts entirely to the backend server or an intermediate L7 device ([§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md) covers this trade-off in depth).
- Because L4 forwarding can preserve the client's original source IP more directly, IP-based security controls further downstream (backend-level allow-lists, per-IP rate limiting) behave differently depending on which layer is in front of them — always verify what the backend actually sees as the "source" before relying on IP-based logic downstream of a load balancer.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                  | Resolution Path                                                                                              |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| Path-based or host-based routing rules silently don't apply        | Load balancer is configured/operating in Layer 4 (TCP) mode, which cannot see HTTP request content | Switch the listener/frontend to Layer 7 (HTTP) mode; confirm TLS is terminated at the LB, not passed through |
| Backend logs show every request coming from the load balancer's IP | Load balancer terminated the connection (L7 proxy behavior) without forwarding client IP header | Enable and read `X-Forwarded-For` (or configure Proxy Protocol for L4) and have the app trust/parse it        |
| Non-HTTP TCP service (database, custom protocol) fails behind LB   | Load balancer is configured in HTTP/L7 mode against a non-HTTP protocol                          | Reconfigure the frontend/listener to Layer 4 (`mode tcp` in HAProxy, a stream/TCP listener elsewhere)         |
| High per-request latency added by the load balancer                | Layer 7 processing overhead (TLS termination, full parsing) on a workload that doesn't need it   | Evaluate whether the workload actually requires L7 features; move to L4 forwarding if not                    |

## 9. Best Practices

- Choose L4 vs. L7 based on what routing logic is actually needed, not by default habit — reach for L7 only when path/host-based routing, cookie-based persistence, or HTTP-aware features ([§77](Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md), [§78](Section-78-Part9-Reverse-Proxies-vs-Load-Balancers-vs-API-Gateways.md)) are genuinely required.
- For raw TCP or UDP workloads (databases, game servers, custom protocols, DNS), default to L4 load balancing — an L7 load balancer generally has no ability to meaningfully process non-HTTP protocols at all.
- When using L7 load balancing, always verify what client-IP-forwarding mechanism (`X-Forwarded-For`, Proxy Protocol) is in place and that backend applications correctly read it, rather than assuming the backend automatically sees the true client IP.

## 10. Common Anti-Patterns / Mistakes

- **Using an HTTP-aware L7 load balancer for a non-HTTP protocol "because that's what we already have."** This either fails outright or requires awkward workarounds (raw TCP mode on an otherwise HTTP-focused product) that erase most of the L7 product's actual value.
- **Assuming an L4 load balancer can enforce content-based security or routing rules.** Teams sometimes discover mid-incident that a firewall or load balancer rule they assumed was inspecting request paths was actually operating purely at L4 and structurally could never have seen that information.
- **Defaulting to L7 for everything without considering the latency and cost overhead.** Not every internal service-to-service call needs path-based routing or cookie persistence; reflexively terminating TLS and fully parsing HTTP at every hop adds unnecessary cost and latency to high-throughput internal traffic.

## 11. Interview Questions

**🎯 Beginner:** _"What's the basic difference between a Layer 4 and a Layer 7 load balancer?"_
**Model answer:** A Layer 4 load balancer makes its routing decision based only on IP addresses and ports, without looking at the actual content of the traffic. A Layer 7 load balancer reads the full application-layer request — for HTTP, that means the URL path, headers, and cookies — and can route based on that content, but it has to fully terminate the connection and parse the protocol to do so.
_What the interviewer is probing for:_ Whether the candidate connects the load-balancing distinction back to the OSI layer vocabulary correctly rather than describing it vaguely.

**🎯 Intermediate:** _"Why would you choose a Layer 4 load balancer over a Layer 7 one, given that Layer 7 offers more routing capability?"_
**Model answer:** Two main reasons: protocol support and performance. Layer 4 load balancing is protocol-agnostic — it works for any TCP or UDP traffic, including databases, custom protocols, and non-HTTP services that an HTTP-aware Layer 7 load balancer simply can't process. It's also lower overhead, since it doesn't need to terminate the connection, decrypt TLS, or parse application data — just forward based on IP/port. If the workload doesn't need path-based or host-based routing, cookie-based persistence, or other HTTP-native features, Layer 4 gets the job done with less latency and lower cost.
_What the interviewer is probing for:_ Practical judgment about matching the tool to the actual requirement rather than assuming "more capable" always means "better choice."

**🎯 Senior:** _"A team's Layer 7 load balancer is terminating TLS, but they want the backend to still know the client's original IP address for audit logging. How does that actually work, and what could go wrong?"_
**Model answer:** Because the L7 load balancer terminates the client's connection and opens a brand-new connection to the backend, the backend would otherwise see the load balancer's own IP as the source. To preserve the real client IP, the load balancer inserts an `X-Forwarded-For` header (or, for non-HTTP L4-with-proxy scenarios, uses the Proxy Protocol) carrying the original client IP, and the backend application must explicitly read and trust that header rather than the raw socket's source address. What can go wrong: if the load balancer isn't the only path into the backend (e.g., the backend is also reachable directly, or sits behind multiple proxy hops), a client can simply set their own `X-Forwarded-For` header and spoof any IP they want, since the header is just application data unless the network topology guarantees it can only be set by a trusted proxy. The backend must only trust that header when it's certain the request could only have arrived via the trusted load balancer.
_What the interviewer is probing for:_ Whether the candidate understands both the mechanism and the spoofing risk it introduces if network topology doesn't structurally prevent bypassing the load balancer.

**🎯 Architect:** _"You're designing ingress for a platform that serves both a high-throughput binary TCP protocol (for a real-time gaming backend) and a standard HTTPS web API. How would you structure load balancing for both?"_
**Model answer:** These have fundamentally different requirements, so I'd use two separate load-balancing layers rather than forcing one tool to do both. For the gaming backend's binary TCP protocol, a Layer 4 load balancer (or a UDP-aware one, if the protocol uses UDP) is the right fit — it's protocol-agnostic, low-latency, and the gaming workload almost certainly doesn't need HTTP-aware routing. For the HTTPS web API, a Layer 7 load balancer terminates TLS, handles path/host-based routing across API services, and can integrate a WAF ([§89](../Part10/Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md)) for content inspection. Both can share underlying infrastructure (the same cloud provider, potentially the same physical load-balancing tier, differentiated by listener/frontend configuration) but conceptually and operationally they should be treated as separate concerns, since collapsing them into a single L7-everywhere or L4-everywhere approach would either break the gaming protocol (LAX doesn't understand its binary format) or lose important HTTP-aware capability for the API traffic.
_What the interviewer is probing for:_ The ability to recognize that L4/L7 isn't a single platform-wide choice — different workloads within the same platform often warrant genuinely different load-balancing layers.

## 12. Common Misconceptions

1. **"Layer 7 load balancing is strictly better than Layer 4."** They serve different purposes; L7's richer routing capability comes with real overhead and protocol constraints that make it the wrong tool for non-HTTP or extremely latency-sensitive workloads.
2. **"A Layer 4 load balancer can't do TLS at all."** It can operate in TLS passthrough mode, forwarding encrypted traffic untouched to the backend, which then terminates TLS itself — the load balancer just never decrypts or inspects the content, which is the defining L4 property, not an inability to handle TLS traffic at all ([§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md) covers this precisely).
3. **"The backend always sees the real client IP by default."** This depends entirely on the load balancer's mode and configuration — L7 proxying in particular requires explicit header forwarding (`X-Forwarded-For`) for the backend to see anything other than the load balancer's own IP.
4. **"Layer 4 and Layer 7 load balancers are always separate physical products."** Modern software load balancers (NGINX, HAProxy, Envoy — [§81](Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md)) and even single cloud products can frequently operate in either mode depending on listener/frontend configuration, rather than requiring an entirely separate appliance for each.

## 13. 🔑 Key Takeaways

- Layer 4 load balancing routes based on IP/port only and is protocol-agnostic; Layer 7 load balancing terminates the connection and routes based on parsed application content (almost always HTTP).
- L7's richer routing capability (path/host-based routing, cookie persistence) comes at the cost of full connection termination, TLS handling overhead, and HTTP-only protocol support.
- L4 is the correct default for non-HTTP TCP/UDP workloads (databases, custom protocols, real-time services); L7 is required whenever routing needs to depend on request content.
- Client IP preservation behaves differently at each layer and requires explicit handling (`X-Forwarded-For`, Proxy Protocol) at L7 in particular.
- Real architectures frequently use both layers together, layered on top of each other, rather than choosing one exclusively for an entire platform.

## 14. Related Concepts & What's Next

[§74](Section-74-Part9-Load-Balancing-Algorithms-Round-Robin-Least-Connections-Weighted-Hashing.md) covers the specific algorithms (round robin, least connections, weighted, hashing) that either layer can use to choose among healthy backends once the L4/L7 routing decision has narrowed the candidate pool. [§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md) expands directly on the TLS termination vs. passthrough trade-off only briefly introduced here. [§80](Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md) maps this exact L4/L7 distinction onto concrete cloud products (NLB vs. ALB, and their Azure/GCP equivalents).

**Next Section:** [§74](Section-74-Part9-Load-Balancing-Algorithms-Round-Robin-Least-Connections-Weighted-Hashing.md) — `Section-74-Part9-Load-Balancing-Algorithms-Round-Robin-Least-Connections-Weighted-Hashing.md`
