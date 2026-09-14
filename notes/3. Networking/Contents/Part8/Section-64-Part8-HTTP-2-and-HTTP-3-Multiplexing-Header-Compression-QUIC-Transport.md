# Section 64 (Part 8): HTTP/2 and HTTP/3: Multiplexing, Header Compression, QUIC Transport

## 1. Definition

**Plain language:** HTTP/2 and HTTP/3 keep the same idea as HTTP/1.1 — a client asks, a server answers — but fix the ways the old plain-text, one-request-at-a-time wire format wasted time. HTTP/2 lets a browser fire many requests down a single connection at once instead of queueing them; HTTP/3 goes further and replaces the underlying TCP connection itself with something faster to establish and more resilient to a dropped packet.

**Precise definition:** **HTTP/2** (RFC 7540, later RFC 9113) is a binary-framed revision of HTTP that runs over a single TCP connection and introduces **multiplexing** — many concurrent request/response **streams** interleaved over that one connection, identified by stream IDs — eliminating the need for multiple TCP connections per origin that HTTP/1.1 relied on to achieve parallelism. It also introduces **HPACK header compression**, which maintains a shared, indexed table of previously-seen header fields between client and server so repeated headers (cookies, user-agent, common request headers) are sent as small references instead of full text on every request. **HTTP/3** (RFC 9114) keeps HTTP/2's semantic model (methods, status codes, headers) but replaces the TCP transport entirely with **QUIC** (RFC 9000), a transport protocol built on top of UDP that implements its own reliability, ordering, and congestion control per stream, along with **TLS 1.3 integrated directly into the transport handshake** rather than layered on top of it separately.

> 💡 **Tip:** The single biggest thing HTTP/2 and HTTP/3 fix is **head-of-line (HOL) blocking** — but at two different layers. HTTP/2 fixes *application-layer* HOL blocking (one slow request no longer blocks other requests on the same connection). HTTP/3 additionally fixes *transport-layer* HOL blocking, because a single lost UDP packet in QUIC only stalls the one stream it belonged to, not every stream multiplexed on the connection — a limitation TCP-based HTTP/2 could never fully escape, since TCP itself guarantees strict in-order delivery across the whole connection.

## 2. Why This Matters

- **Performance at scale is directly tied to these mechanics.** Page load time, API latency under concurrent calls, and mobile network resilience (where packet loss is common) are all measurably affected by whether a service runs HTTP/1.1, HTTP/2, or HTTP/3 — this isn't an academic distinction for infrastructure engineers tuning production services.
- **Load balancer and CDN configuration decisions hinge on protocol support.** Enabling HTTP/2 or HTTP/3 termination, ALPN negotiation, and upstream protocol choice are real, consequential settings on every major load balancer and CDN ([§76](../Part9/Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md), [§80](../Part9/Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md), [§81](../Part9/Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md) in Part 9).
- **QUIC's move to UDP changes firewall and network-appliance assumptions.** Security groups, stateful firewalls ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md), Part 10), and some corporate/ISP middleboxes historically treat UDP differently from TCP, and HTTP/3 adoption has real operational implications for anything that inspects or filters traffic by port/protocol.
- **Debugging tools and mental models differ across versions.** A `tcpdump` capture of HTTP/2 traffic looks nothing like HTTP/1.1's readable plain text ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) — it's binary framed — and HTTP/3 traffic is encrypted UDP from the very first packet, requiring different diagnostic approaches entirely ([§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md), [§119](../Part14/Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md), Part 14).
- **Certificate and TLS configuration is now inseparable from transport configuration in HTTP/3**, since QUIC mandates TLS 1.3 as part of the transport handshake itself rather than as an optional add-on — this changes how engineers reason about the relationship between [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) (TLS) and the application protocol.

## 3. Prerequisites and Dependencies

This section directly builds on [§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)'s coverage of HTTP/1.1 request/response semantics, methods, and status codes — HTTP/2 and HTTP/3 preserve all of that vocabulary unchanged and only change how requests and responses travel across the network, so [§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md) should be read first. A working understanding of the TCP three-way handshake and TCP's guarantees ([§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md), [§56](../Part7/Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md), Part 7) is necessary to appreciate exactly what QUIC changes and why; similarly, UDP's connectionless, unordered delivery model ([§58](../Part7/Section-58-Part7-UDP-Structure-Use-Cases-and-Trade-Offs-vs-TCP.md), Part 7) is the foundation QUIC is built on top of. [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) (TLS/SSL Fundamentals) is a close companion to this section since HTTP/2 in practice is almost always deployed over TLS (browsers require it) and HTTP/3/QUIC mandates TLS 1.3 integration structurally — reading [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) alongside or shortly after this section will make the "0-RTT" and integrated-handshake concepts introduced here concrete.

## 4. Architecture / Conceptual Diagram

```text
   HTTP/1.1 (§63)                HTTP/2                         HTTP/3

   Conn 1: ──► GET /a            Single TCP connection:         Single QUIC connection (over UDP):
           ◄── resp /a           Stream 1: GET /a ──►           Stream 1: GET /a ──►
   Conn 2: ──► GET /b                      GET /b ──►                    GET /b ──►
           ◄── resp /b                     GET /c ──►                    GET /c ──►
   Conn 3: ──► GET /c                                                    (independent per-stream
           ◄── resp /c            ◄── resp /b (out of order OK)           loss recovery — one
                                  ◄── resp /a                              dropped packet stalls
   (needs multiple TCP           ◄── resp /c                              only ITS stream, not
    connections for               (all interleaved as binary               the whole connection)
    real parallelism —            frames, HPACK-compressed
    or HOL blocking on            headers, on ONE connection —
    one connection)               no HOL blocking at the
                                  HTTP layer, but a single
                                  lost TCP segment still
                                  stalls ALL streams — TCP
                                  itself has no concept of
                                  independent streams)

   Transport: TCP                Transport: TCP                 Transport: QUIC (UDP-based),
                                                                 TLS 1.3 built into the
                                                                 handshake itself, supports
                                                                 0-RTT resumption
```

- **HTTP/2's binary framing layer** breaks each request/response into typed frames (HEADERS, DATA, SETTINGS, etc.), tagged with a stream ID, allowing the receiver to reassemble multiple concurrent streams from a single ordered byte stream — this is what enables multiplexing without needing multiple TCP connections.
- **HPACK** solves a real HTTP/1.1 inefficiency: modern requests carry large, highly repetitive headers (cookies, auth tokens, user-agent strings) on every single request; HPACK's shared compression table means only the first occurrence needs to be sent in full, with later requests referencing it by a small index.
- **QUIC's per-stream independence** is the structural fix for TCP's fundamental limitation in this context: TCP guarantees strict in-order byte delivery for the *entire* connection, so a single lost/delayed TCP segment stalls every HTTP/2 stream multiplexed on top of it, even ones with no relationship to the lost data — QUIC's own stream abstraction avoids this by tracking loss and retransmission per stream, not per connection.

## 5. Hands-On

### 5.1 Confirming Which HTTP Version a Server Negotiated

**Purpose:** Show that protocol version selection happens via TLS ALPN (Application-Layer Protocol Negotiation) during the handshake, and how to observe the result.

**Syntax:**

```bash
curl -v --http2 <url>
```

**Example usage and expected output:**

```bash
$ curl -v --http2 https://www.google.com/
* ALPN: offers h2,http/1.1
* ALPN: server accepted h2
* using HTTP/2
> GET / HTTP/2
> host: www.google.com
> user-agent: curl/8.4.0
>
< HTTP/2 200
< content-type: text/html; charset=UTF-8
```

- `ALPN: offers h2,http/1.1` shows the client advertising both protocol options during the TLS handshake; `server accepted h2` confirms the server chose HTTP/2 for this connection — this negotiation happens before a single HTTP request byte is sent.
- Note the lower-case header field names (`host`, `user-agent`) in HTTP/2 output — the binary framing format normalizes header names to lowercase, unlike HTTP/1.1's traditionally mixed-case convention (`Host`, `User-Agent`), though both are semantically equivalent.

**Production usage example:** Confirming actual negotiated protocol version end-to-end (not just what a CDN's edge advertises, but what the origin server itself speaks) is a standard step when diagnosing performance regressions after a load balancer or CDN configuration change — a misconfigured upstream can silently fall back to HTTP/1.1 even when the edge advertises HTTP/2 or HTTP/3 to clients.

**Common errors:** Assuming a server supports HTTP/2 just because the client requested it — `curl --http2` requests HTTP/2 but gracefully falls back to HTTP/1.1 if the server doesn't support it or if ALPN negotiation fails, and the fallback is easy to miss without checking the `< HTTP/2` vs `< HTTP/1.1` line in the actual response.

### 5.2 Testing HTTP/3 (QUIC) Support

**Purpose:** Demonstrate that HTTP/3 requires explicit client and transport support, and how servers advertise it to clients already connected over HTTP/2.

**Syntax:**

```bash
curl -v --http3 <url>
```

**Example usage and expected output:**

```bash
$ curl -v --http3 https://cloudflare-quic.com/
* Connecting to 104.16.132.229 port 443 (QUIC)
* QUIC connection established
> GET / HTTP/3
> host: cloudflare-quic.com
>
< HTTP/3 200
< alt-svc: h3=":443"; ma=86400
```

- The `alt-svc: h3=":443"` response header is how a server tells a client, over an existing HTTP/1.1 or HTTP/2 connection, "I also support HTTP/3 on this same port — feel free to try QUIC next time." This is how browsers discover HTTP/3 support without needing it hard-coded, since QUIC uses UDP and cannot simply "upgrade" an existing TCP connection.
- `curl` requires being built with QUIC library support (`--http3` fails with "option not supported" otherwise) — this is a meaningfully less universal capability than `--http2`, reflecting HTTP/3's comparatively newer, less ubiquitous deployment.

**Production usage example:** CDN and load balancer teams use `alt-svc` advertisement plus explicit HTTP/3 client testing to validate a phased HTTP/3 rollout — advertising support to a subset of traffic first and confirming actual QUIC connections establish successfully before flipping it on for all clients.

**Common errors:** Assuming HTTP/3 failures are application bugs when they are frequently network-path issues — some corporate networks, older NAT devices, and restrictive firewalls block or throttle UDP traffic on port 443 far more aggressively than TCP, causing QUIC connections to silently fail or fall back, which looks identical to "slow site" from a user's perspective without packet-level inspection ([§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md)).

## 6. Production Usage Notes

- **HTTP/2 is effectively universal for TLS-terminating load balancers, CDNs, and modern web servers today**; enabling it is usually a configuration flag (NGINX's `listen 443 ssl http2;`, or equivalent on cloud load balancers, [§80](../Part9/Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md)) rather than an application code change, since the semantic layer (methods, headers, status codes) is unchanged from HTTP/1.1.
- **HTTP/3 adoption is more selective and often edge-only.** A common production pattern is HTTP/3 between client and CDN/edge, with HTTP/2 or even HTTP/1.1 between the edge and origin servers — the origin never needs to speak QUIC directly, since the edge terminates the client-facing protocol and re-encodes the request for the backend.
- **Multiplexing changes concurrency assumptions for backend services.** A backend that previously received requests spread across several TCP connections per client may now see many logically-concurrent requests arriving multiplexed over what looks, at the TCP layer, like a single connection from the load balancer — connection-count-based rate limiting or per-connection resource allocation needs re-examining under HTTP/2/3.

## 7. Security Considerations

- **QUIC's mandatory TLS 1.3 integration removes an entire historical attack surface**: there is no such thing as "plaintext HTTP/3" the way plaintext HTTP/1.1 exists on port 80 — every QUIC connection is encrypted by protocol design, not by operator choice.
- **UDP-based transport changes DDoS mitigation posture.** Historically, UDP has been a common vector for reflection/amplification DDoS attacks ([§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md), Part 10) precisely because it's connectionless and easy to spoof source addresses on; QUIC includes anti-amplification limits in its handshake specifically to reduce this risk, but network operators still need to treat UDP port 443 traffic with the same seriousness as any other production-critical protocol port.
- **HPACK header compression has a known historical class of vulnerabilities (CRIME/BREACH-adjacent compression side-channel attacks)** when compression mixes attacker-controlled and secret data; HTTP/2 server implementations mitigate this with restrictions on what gets compressed together, but it's a reason header compression schemes need careful implementation, not something to assume is automatically safe.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                    | Resolution Path                                                                                                    |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| A client on a corporate/hotel network reports the site is slow or fails, but works fine elsewhere | UDP port 443 (QUIC/HTTP/3) is blocked or throttled by that network, and the browser is stalling before falling back | Confirm expected fallback behavior to HTTP/2 over TCP; verify `alt-svc` and client fallback timeouts are tuned reasonably |
| Backend sees far more "concurrent" requests per client connection than expected | HTTP/2 multiplexing is legitimately sending many streams over one connection from a load balancer/proxy | Re-tune concurrency and rate-limiting logic to count requests/streams, not TCP connections                          |
| `curl --http2` silently falls back to HTTP/1.1 against an internal service | The internal service or its TLS termination point doesn't support ALPN negotiation for `h2`      | Verify the web server/load balancer configuration explicitly enables HTTP/2 and that ALPN is functioning in the TLS handshake ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) |
| Packet captures of HTTP/2 traffic are unreadable in a text-based capture tool | HTTP/2 is a binary framing format, unlike HTTP/1.1's plain text                                  | Use a decoder aware of HTTP/2 framing (Wireshark's HTTP/2 dissector, [§119](../Part14/Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md)) rather than reading raw bytes as text     |

## 9. Best Practices

- Enable HTTP/2 at every TLS-terminating point in the infrastructure (load balancer, CDN, web server) as a default rather than an opt-in — the performance benefit is broad and the configuration cost is typically minimal on modern software.
- When rolling out HTTP/3, do so incrementally at the edge/CDN layer first, and monitor for network-path-related fallback failures (corporate proxies, older NAT/firewall devices) rather than assuming universal client support.
- Re-audit any concurrency, connection-count, or rate-limiting logic that was written assuming one request per TCP connection (an HTTP/1.1-era assumption) before enabling HTTP/2 or HTTP/3 on a service that depends on that logic.

## 10. Common Anti-Patterns / Mistakes

- **Assuming HTTP/2 or HTTP/3 automatically "fixes" all latency problems.** They eliminate specific classes of overhead (connection setup cost, head-of-line blocking) but do nothing for slow application logic, slow databases, or poorly designed APIs — protocol upgrades are not a substitute for addressing actual bottlenecks.
- **Building rate limiting or resource allocation logic around TCP connection count** in a world where HTTP/2 multiplexes many logical requests over one connection — this dramatically undercounts real concurrent load per client.
- **Treating HTTP/3 as a drop-in replacement with zero operational differences.** Its UDP-based transport genuinely behaves differently across NAT devices, firewalls, and some corporate networks, and needs its own explicit rollout and monitoring plan rather than being flipped on and forgotten.

## 11. Interview Questions

**🎯 Beginner:** _"What is the main improvement HTTP/2 introduced over HTTP/1.1?"_
**Model answer:** HTTP/2 introduces multiplexing — multiple requests and responses can be sent concurrently, interleaved as binary frames, over a single TCP connection, instead of needing multiple TCP connections (or waiting sequentially) to get parallelism the way HTTP/1.1 typically requires. It also adds HPACK header compression to reduce repeated header overhead.
_What the interviewer is probing for:_ Basic familiarity with why HTTP/2 exists and what specific problem it solves, not just that "it's faster."

**🎯 Intermediate:** _"Why does HTTP/3 replace TCP with QUIC instead of just running HTTP/2's multiplexing model over TCP?"_
**Model answer:** Because TCP itself guarantees strict in-order byte delivery for the whole connection — even though HTTP/2 multiplexes multiple logical streams over that connection, a single lost or delayed TCP segment stalls every stream, since TCP has no concept of independent streams at its own layer. This is called transport-layer head-of-line blocking, and no amount of clever framing at the HTTP layer can fix it while still running over TCP. QUIC solves this by implementing its own reliability and ordering per-stream, on top of UDP, so a lost packet only stalls the one stream it belonged to.
_What the interviewer is probing for:_ Understanding the actual layered reason HTTP/3 needed a new transport, not just "QUIC is newer/faster."

**🎯 Senior:** _"Your team notices that after enabling HTTP/3 on your CDN, a subset of users on corporate networks report degraded performance. How do you investigate and what's the likely explanation?"_
**Model answer:** I'd start by checking whether those users are actually connecting via HTTP/3 or falling back — many corporate firewalls and proxies block or heavily throttle UDP traffic on port 443 since it's newer and less universally allow-listed than TCP/443, which HTTP/3 relies on for QUIC. A poorly tuned client fallback (waiting too long before giving up on QUIC and retrying over TCP/HTTP-2) can make this look like "HTTP/3 makes things slower" when the real problem is the client stalling on a blocked UDP path before falling back. I'd verify with packet captures on an affected network whether QUIC handshake packets are actually leaving the client, check `alt-svc` behavior, and consider whether the CDN's fallback/retry timeout needs shortening for this rollout.
_What the interviewer is probing for:_ Real production experience distinguishing "protocol theoretically supports this" from "network paths actually cooperate," and diagnostic rigor rather than guessing.

**🎯 Architect:** _"You're designing the edge architecture for a global, latency-sensitive API platform. How do HTTP/2 and HTTP/3 factor into your load balancer and CDN protocol strategy?"_
**Model answer:** I'd terminate TLS 1.3 at the edge with both HTTP/2 and HTTP/3 (via `alt-svc` advertisement) enabled for client-facing connections, since HTTP/3's per-stream loss recovery meaningfully helps clients on lossy mobile networks, which is a large share of global traffic. Between edge and origin, I'd likely keep HTTP/2 rather than requiring HTTP/3 all the way through, since the edge-to-origin path is typically a stable, low-loss, high-bandwidth link where QUIC's benefits are marginal and HTTP/2's broader server-side support is simpler to operate. I'd re-audit backend concurrency and rate-limiting logic to be stream-aware rather than connection-count-based, and I'd build explicit UDP-path health monitoring separate from TCP-path monitoring, since QUIC failures manifest differently (silent stalls, not connection refused) and need their own alerting. Finally, I'd treat HTTP/3 rollout as staged and reversible via `alt-svc` toggling, not an irreversible cutover.
_What the interviewer is probing for:_ Whether the candidate can reason about protocol choice as an architectural trade-off across the whole request path, not just as a checkbox feature to enable everywhere.

## 12. Common Misconceptions

1. **"HTTP/2 and HTTP/3 change what an HTTP request or response contains."** They don't — methods, status codes, and header semantics ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) are preserved; only the wire format and transport mechanics change.
2. **"HTTP/3 is just HTTP/2 over UDP."** HTTP/3 fundamentally changes the transport to QUIC, which implements its own reliability and per-stream loss recovery — it is not simply HTTP/2's TCP-based multiplexing model relocated onto UDP.
3. **"Enabling HTTP/2 automatically means every request is now faster."** It removes specific overheads (connection setup, header redundancy, one class of head-of-line blocking) but does nothing to speed up slow backend processing.
4. **"QUIC being UDP-based makes it less reliable than TCP."** QUIC implements its own robust reliability, ordering, and congestion control on top of UDP — it is not "unreliable" in the way raw UDP is; it simply builds those guarantees per-stream rather than inheriting TCP's connection-wide guarantee.

## 13. 🔑 Key Takeaways

- HTTP/2 introduces binary framing, multiplexing (many streams over one TCP connection), and HPACK header compression, while preserving HTTP/1.1's request/response and status-code semantics unchanged ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)).
- HTTP/3 preserves HTTP/2's semantic model but replaces TCP with QUIC, a UDP-based transport with its own per-stream reliability, ordering, and integrated TLS 1.3 handshake.
- The core problem HTTP/2 solves is application-layer head-of-line blocking; the core problem HTTP/3 additionally solves is transport-layer head-of-line blocking, which HTTP/2 could not escape while still running over TCP.
- Protocol version negotiation happens via TLS ALPN for HTTP/2, and via `alt-svc` advertisement plus a separate QUIC handshake attempt for HTTP/3 — the two mechanisms are architecturally different.
- QUIC's UDP-based transport has real, distinct operational implications for firewalls, NAT devices, and DDoS posture that TCP-based HTTP/1.1/HTTP/2 traffic does not carry.

## 14. Related Concepts & What's Next

[§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) introduces TLS/SSL in depth, which is a structural prerequisite for HTTP/3 (QUIC mandates TLS 1.3 as part of its own handshake) and a near-universal deployment companion for HTTP/2. [§76](../Part9/Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md) and [§80](../Part9/Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md) (Part 9) cover how load balancers and cloud load balancer products handle protocol termination and upstream protocol selection, directly building on the negotiation mechanics introduced here. [§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) (Part 10) covers stateful vs. stateless firewall filtering, relevant to understanding why UDP-based QUIC traffic is sometimes treated differently by network security appliances than TCP traffic. [§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md) and [§119](../Part14/Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md) (Part 14) cover packet capture and Wireshark analysis, which are the practical tools needed to actually inspect HTTP/2's binary framing or HTTP/3's encrypted QUIC packets when troubleshooting beyond what `curl -v` can show.

**Next Section:** [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) — `Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md`
