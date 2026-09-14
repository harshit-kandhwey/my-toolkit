# Section 63 (Part 8): HTTP/1.1 Fundamentals: Requests, Responses, Methods, Status Codes

## 1. Definition

**Plain language:** HTTP is the plain-text conversation format that a browser (or `curl`, or a service calling another service) uses to ask a server for something and the server uses to answer back. A request says what you want and how; a response says what happened and hands back the data. Almost everything running on the modern web — REST APIs, static websites, health checks, webhooks — is HTTP requests and responses underneath.

**Precise definition:** **HTTP (Hypertext Transfer Protocol) version 1.1**, standardized in RFC 2616 and later refined into RFC 7230–7235, is a text-based, stateless, request-response **application-layer protocol** that runs on top of a reliable transport — almost always TCP ([§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)), on port 80 for plaintext or layered inside TLS ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) on port 443 for HTTPS. Each HTTP transaction consists of a **request** (a method, a target URI, a protocol version, a set of header fields, and an optional body) sent from client to server, and a **response** (a protocol version, a numeric status code, a reason phrase, headers, and an optional body) sent back. HTTP/1.1's defining improvements over HTTP/1.0 are **persistent connections** (`Connection: keep-alive` by default, avoiding a new TCP handshake per request) and **chunked transfer encoding** (streaming a response body of unknown length without needing a `Content-Length` header up front).

> 💡 **Tip:** HTTP is stateless by design — the protocol itself has no concept of "this request is related to that earlier request from the same user." Every mechanism that feels like state (login sessions, shopping carts) is bolted on top using cookies, tokens, or server-side session stores; HTTP itself never remembers anything between requests.

## 2. Why This Matters

- **It is the substrate of virtually all modern infrastructure traffic.** Load balancers (Part 9), API gateways, service meshes, health checks, and CI/CD webhook deliveries are all HTTP requests and responses at their core — understanding the request/response model is a prerequisite for reasoning about almost any application-layer problem.
- **Status codes are the first diagnostic signal in any outage.** A `502` versus a `504` versus a `403` tells a completely different troubleshooting story, and misreading which layer produced the code (the app, a proxy, or a load balancer) wastes significant incident time.
- **Methods encode intent, and infrastructure tooling depends on that intent being honest.** Caches, proxies, and retries all make decisions based on whether a method is safe and idempotent (`GET` vs. `POST`) — violating those semantics breaks caching layers and retry logic in ways that are hard to trace back to the root cause.
- **Headers carry the metadata that load balancers, CDNs, and WAFs act on.** `Host`, `Content-Type`, `Authorization`, and caching headers are inspected and sometimes rewritten by every proxy in the path; understanding raw HTTP is what makes debugging a proxy's behavior possible.
- **It is the foundation HTTP/2 and HTTP/3 build on.** [§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md) covers how those later versions change the transport mechanics while preserving the same request/response semantics defined here — none of that makes sense without this section first.

## 3. Prerequisites and Dependencies

This section assumes the transport-layer foundation built across Part 7 ([§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)), particularly the TCP three-way handshake ([§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)) and the concept of ports and sockets ([§59](../Part7/Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md)) — HTTP/1.1 rides directly on top of a TCP connection and its request/response cycle is meaningless without that connection already established. Basic familiarity with DNS resolution (Part 6, [§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)–[§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md)) is also assumed, since every HTTP request begins with resolving a hostname to an IP address before a connection can even be attempted. This section does not assume any encryption knowledge — TLS is introduced separately in [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) and layered on top of the plain-text HTTP mechanics covered here. [§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md) immediately follows with HTTP/2 and HTTP/3, which change the wire format and transport but preserve the request/response, method, and status-code vocabulary defined in this section unchanged.

## 4. Architecture / Conceptual Diagram

```text
   CLIENT                                            SERVER

   1. DNS resolve hostname (§44-§53)
   2. TCP handshake to port 80/443 (§55)
              │
              ▼
   ┌─────────────────────────────┐
   │ HTTP REQUEST                │
   │ GET /api/users/42 HTTP/1.1  │  ◄── Request line: method, target, version
   │ Host: api.example.com       │  ◄── Headers
   │ Accept: application/json    │
   │ Authorization: Bearer ...   │
   │ (empty line)                │
   │ (optional body)             │
   └─────────────────────────────┘
              │
              ►  sent over the established TCP connection
              │
   ┌─────────────────────────────┐
   │ HTTP RESPONSE                │
   │ HTTP/1.1 200 OK              │  ◄── Status line: version, code, reason
   │ Content-Type: application/json│  ◄── Headers
   │ Content-Length: 87           │
   │ (empty line)                 │
   │ {"id":42,"name":"..."}       │  ◄── Body
   └─────────────────────────────┘
              ◄
   3. Connection kept alive (persistent, HTTP/1.1 default) for the next request
      or closed if `Connection: close` was sent
```

- The **request line** and **status line** are the only mandatory single lines; everything else is a variable set of `Name: Value` header fields, terminated by a blank line (`\r\n\r\n`) before any body begins.
- **Persistent connections** mean a single TCP connection commonly carries many sequential request/response pairs, which is why connection reuse and connection-pool sizing matter for both clients (HTTP client libraries) and servers (worker/thread limits) under load.
- **Pipelining** (sending multiple requests without waiting for each response) was defined in HTTP/1.1 but is almost universally disabled in practice due to head-of-line blocking and buggy intermediary support — this is one of the core problems HTTP/2's multiplexing ([§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) was designed to solve properly.

## 5. Hands-On

### 5.1 Making a Raw HTTP Request and Reading the Full Response with `curl -v`

**Purpose:** See the literal request line, headers, and status line HTTP sends over the wire, not just the rendered body.

**Syntax:**

```bash
curl -v <url>
```

**Example usage and expected output:**

```bash
$ curl -v http://example.com/
* Connected to example.com (93.184.216.34) port 80
> GET / HTTP/1.1
> Host: example.com
> User-Agent: curl/8.4.0
> Accept: */*
>
< HTTP/1.1 200 OK
< Content-Type: text/html; charset=UTF-8
< Content-Length: 1256
< Connection: keep-alive
<
<!doctype html>
<html>...
```

- Lines prefixed `>` are exactly what `curl` sent (the request); lines prefixed `<` are exactly what came back (the response) — this is the ground truth for what actually crossed the wire, independent of any client-library abstraction.
- The blank line after the last `>` header marks the end of the request headers, and the blank line after the last `<` header marks the end of the response headers, matching the diagram above.

**Production usage example:** `curl -v` is the first tool reached for whenever a service-to-service HTTP call behaves unexpectedly — confirming the exact `Host` header sent, whether `Authorization` made it through a proxy, and the literal status line returned removes any ambiguity introduced by higher-level HTTP client libraries that may retry, redirect, or swallow errors silently.

**Common errors:** Forgetting `-v` and only seeing the rendered body leaves no way to distinguish "the server returned an error page with a 200 status" from "the server returned a genuine error status" — always check the status line explicitly, especially when debugging automation that only checks HTTP status codes rather than parsing body content.

### 5.2 Testing Methods and Status Codes Explicitly

**Purpose:** Demonstrate how method choice and status codes communicate intent and outcome independently of the response body.

**Syntax:**

```bash
curl -X <METHOD> -i <url>
```

**Example usage and expected output:**

```bash
$ curl -X POST -i https://api.example.com/orders -d '{"item":"widget"}'
HTTP/1.1 201 Created
Location: /orders/9931
Content-Type: application/json

{"id":9931,"item":"widget","status":"pending"}

$ curl -X DELETE -i https://api.example.com/orders/9931
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error":"order not found"}
```

- `POST` is neither safe nor idempotent — calling it twice can create two orders, which is exactly why `201 Created` returns a `Location` header pointing at the new resource, distinguishing this from an idempotent `PUT`.
- `GET`, `HEAD`, `PUT`, and `DELETE` are all defined as idempotent (repeating the same request produces the same server-side end state), which is precisely why load balancers and HTTP client libraries feel safe automatically retrying them on transient network failures but never automatically retry a bare `POST`.
- The `404` on the second call illustrates that status codes fall into families: `2xx` success, `3xx` redirection, `4xx` client error, `5xx` server error — the first digit alone tells an automated system (or an on-call engineer) which side of the connection to start investigating.

**Production usage example:** API design and infrastructure automation both lean on this: an API gateway or load balancer's health check expects a `2xx` from `GET /healthz`; a CI/CD pipeline step that calls a deployment webhook checks specifically for `2xx` versus `5xx` to decide whether to retry or halt the pipeline ([§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md), Part 9 covers health checks in the load-balancing context more fully).

**Common errors:** Treating all non-2xx responses as equivalent failures is a common automation bug — a `429 Too Many Requests` should trigger a backoff-and-retry, while a `400 Bad Request` means the request itself is malformed and retrying identically will never succeed; conflating the two produces either wasted retries or premature failure.

## 6. Production Usage Notes

- **Persistent connections are the default in HTTP/1.1**, but many infrastructure components (older load balancers, certain proxy configurations) still default to closing connections aggressively; verifying `Connection: keep-alive` behavior end-to-end through every hop matters for latency-sensitive services, since re-establishing a TCP (and TLS, [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) handshake per request is expensive.
- **Header size and count limits are a real production constraint.** Web servers and proxies (NGINX, HAProxy, cloud load balancers) all enforce maximum header sizes; a client sending an oversized `Authorization` header (a very large JWT, for instance) can trigger a `431 Request Header Fields Too Large` that is easy to misdiagnose as an application bug.
- **`Host` header correctness is what makes virtual hosting work** — a single IP address and port can serve many different domains because the server (or the load balancer/reverse proxy in front of it, [§78](../Part9/Section-78-Part9-Reverse-Proxies-vs-Load-Balancers-vs-API-Gateways.md)) routes based on the `Host` header value in the request, not the destination IP alone.

## 7. Security Considerations

- **Plain HTTP (port 80, no TLS) transmits every header and body in cleartext**, including `Authorization` headers and cookies — anyone on the network path (a compromised router, a malicious Wi-Fi access point) can read or modify it; this is why [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)'s TLS handshake and HTTPS-only policies are treated as a baseline requirement, not an optional hardening step, for any traffic carrying credentials.
- **Method misuse is a common attack surface.** Using `GET` for state-changing operations means the action can be triggered by simply visiting a link or having it cached/pre-fetched by a browser or proxy, and is a classic building block of CSRF (Cross-Site Request Forgery) attacks — REST API design conventions exist partly to prevent this class of mistake.
- **Overly verbose error responses leak information.** A `500` response body that includes a stack trace, internal hostnames, or database error text hands an attacker reconnaissance data for free; production services should return generic `4xx`/`5xx` bodies externally and log the detailed error server-side only.

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Likely Cause                                                                 | Resolution Path                                                                                     |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Client gets `400 Bad Request` with no obvious malformed input   | A proxy or load balancer in the path is rejecting the request before it reaches the app (oversized header, malformed `Host`) | Use `curl -v` directly against the origin server, bypassing the proxy, to isolate which hop produced the `400` |
| Requests intermittently hang for several seconds before completing | Connection reuse isn't happening; a new TCP (and possibly TLS) handshake is being paid for on every request | Verify `Connection: keep-alive` is honored end-to-end and that client connection pooling is configured correctly |
| API consumer reports `POST` requests sometimes creating duplicate records | An automatic retry (client library or proxy) is resending a non-idempotent `POST` after a timeout, unaware the first attempt actually succeeded server-side | Make the endpoint idempotent via an idempotency key, or restrict automatic retries to genuinely idempotent methods |
| Browser shows a cached, stale version of a page after a deploy   | Caching headers (`Cache-Control`, `ETag`) are too permissive or absent, and an intermediary cache/CDN served a stale copy | Set explicit cache-control policy per resource and verify with `curl -I` that headers match intent          |

## 9. Best Practices

- Use HTTP methods according to their defined semantics (`GET` for retrieval with no side effects, `POST` for creation/non-idempotent actions, `PUT`/`DELETE` for idempotent replace/remove) so that caches, proxies, and retry logic throughout the stack behave correctly without special-casing your API.
- Return specific, correct status codes rather than defaulting everything to `200` with an error flag in the body — infrastructure (load balancers, monitoring, CDNs, `curl`-based health checks) makes real routing and alerting decisions based on the status line alone.
- Always verify raw request/response behavior with `curl -v` or an equivalent tool when debugging anything HTTP-related, rather than trusting only what a high-level client library or browser dev tools panel summarizes — the raw wire format is the ground truth.

## 10. Common Anti-Patterns / Mistakes

- **Using `GET` for operations with side effects.** This breaks caching assumptions, enables CSRF-style attacks, and causes accidental data mutation whenever a crawler, browser prefetcher, or link-preview bot follows the URL.
- **Treating HTTP status codes as decorative rather than semantic.** Returning `200 OK` for every response, including actual failures, forces every consumer to parse the response body just to know if the call succeeded — defeating the purpose of having a status line at all.
- **Ignoring `Connection` and keep-alive behavior when building high-throughput clients.** Opening a fresh TCP connection (and TLS handshake, [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) per request under load is a very common, very avoidable source of latency and connection exhaustion in production services.

## 11. Interview Questions

**🎯 Beginner:** _"What are the main parts of an HTTP request and an HTTP response?"_
**Model answer:** A request has a request line (method, target URI, HTTP version), a set of headers, and an optional body. A response has a status line (HTTP version, numeric status code, reason phrase), a set of headers, and an optional body. Both are separated from their body by a blank line.
_What the interviewer is probing for:_ Basic fluency with HTTP's wire format, not just familiarity with using a browser or REST client.

**🎯 Intermediate:** _"Explain the difference between idempotent and safe HTTP methods, and why that distinction matters operationally."_
**Model answer:** A safe method (`GET`, `HEAD`) has no side effects on the server — it only retrieves data. An idempotent method (`GET`, `HEAD`, `PUT`, `DELETE`) produces the same server-side end state no matter how many times it's repeated, even though it may have side effects the first time. `POST` is neither. This matters operationally because load balancers, HTTP client libraries, and proxies use these properties to decide what's safe to automatically retry after a timeout or connection failure — retrying an idempotent `PUT` is safe, but blindly retrying a `POST` can create duplicate resources.
_What the interviewer is probing for:_ Whether the candidate connects protocol semantics to real infrastructure behavior (retries, caching) rather than reciting definitions.

**🎯 Senior:** _"A service behind a load balancer occasionally returns `502 Bad Gateway` under load, but the application logs show no errors. Walk through your diagnosis."_
**Model answer:** A `502` means the load balancer/proxy successfully received a response header from upstream but that response was invalid or the connection to upstream failed — critically, this status code is generated by the proxy, not the application, which is exactly why application logs show nothing. I'd check the load balancer's own logs for the specific upstream error (connection reset, timeout, malformed response), check whether the app's keep-alive timeout is shorter than the proxy's, which causes the proxy to reuse a connection the app already closed, and check whether the app is exceeding a worker/connection limit under load and dropping connections mid-response. The key insight is to stop looking in the app and start looking at the layer that actually emitted the status code.
_What the interviewer is probing for:_ Understanding that intermediary-generated status codes point troubleshooting at the proxy/gateway layer, not the origin server — a very common real production scenario.

**🎯 Architect:** _"You're designing a public API. What HTTP-level decisions do you make to keep it reliable and debuggable at scale, beyond just picking correct status codes?"_
**Model answer:** I'd standardize idempotency keys for non-idempotent state-changing endpoints so clients can safely retry `POST` calls without risk of duplication. I'd define a consistent error body schema across all `4xx`/`5xx` responses so clients can programmatically distinguish error types beyond the status code alone. I'd set explicit, resource-appropriate `Cache-Control` headers rather than relying on defaults, since caching behavior compounds unpredictably across CDNs and client caches otherwise. I'd ensure `Connection`/keep-alive behavior is tuned consistently across every hop (client, load balancer, app server) to avoid connection churn under load. And I'd make sure the status codes returned by any fronting proxy or load balancer (502/503/504) are distinguishable in monitoring from status codes returned by the application itself, since they point to entirely different failure domains.
_What the interviewer is probing for:_ Systems-level thinking about how raw HTTP semantics ripple through an entire distributed architecture, not just single-request correctness.

## 12. Common Misconceptions

1. **"HTTP is inherently stateful because of sessions and cookies."** The protocol itself is stateless; sessions, cookies, and tokens are application-layer conventions built on top of HTTP, not part of the protocol's own state model.
2. **"A `200` status always means the operation genuinely succeeded."** Some APIs incorrectly return `200` with an error flag embedded in the body, which defeats the purpose of status codes and forces every consumer to parse the body to know the real outcome.
3. **"HTTP/1.1 always opens a new TCP connection per request."** This was true of HTTP/1.0's default behavior; HTTP/1.1 defaults to persistent connections specifically to avoid that cost, reusing one TCP connection for many sequential requests.
4. **"`POST` and `PUT` are interchangeable for creating resources."** They carry different idempotency guarantees — `PUT` is expected to be idempotent (repeating it produces the same end state), while `POST` is not, and infrastructure tooling (retries, caches) relies on that distinction being honored.

## 13. 🔑 Key Takeaways

- HTTP/1.1 is a text-based, stateless, request-response protocol running over TCP ([§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)), consisting of a request (method, target, headers, optional body) and a response (status line, headers, optional body).
- HTTP/1.1's key advances over HTTP/1.0 are persistent connections by default and chunked transfer encoding, both aimed at reducing per-request overhead.
- Methods carry semantic guarantees (safe, idempotent) that caches, proxies, and retry logic throughout production infrastructure depend on being honored correctly.
- Status codes are grouped by family (`2xx`/`3xx`/`4xx`/`5xx`) and the layer that generates a given code (application vs. proxy/load balancer) is critical diagnostic information, especially for `502`/`503`/`504`.
- Raw wire-level inspection with `curl -v` is the ground-truth debugging tool for any HTTP behavior a higher-level client library or browser might otherwise obscure.

## 14. Related Concepts & What's Next

[§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md) builds directly on this section by showing how HTTP/2 and HTTP/3 preserve the request/response and status-code model defined here while completely re-engineering the underlying transport mechanics (binary framing, multiplexing, and for HTTP/3, replacing TCP with QUIC). [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) introduces TLS, the encryption layer that turns plain HTTP into HTTPS and protects the headers and bodies described here from being read or tampered with in transit. [§78](../Part9/Section-78-Part9-Reverse-Proxies-vs-Load-Balancers-vs-API-Gateways.md) (Part 9) revisits HTTP semantics from the perspective of reverse proxies, load balancers, and API gateways, all of which inspect and sometimes rewrite the exact request/response structure covered in this section. [§89](../Part10/Section-89-Part10-Web-Application-Firewalls-WAF-Conceptual-Overview.md) (Part 10) covers Web Application Firewalls, which inspect Layer 7 HTTP content — the methods, headers, and bodies introduced here — to detect and block malicious requests.

**Next Section:** [§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md) — `Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md`
