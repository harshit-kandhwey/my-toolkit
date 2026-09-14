# Section 70 (Part 8): WebSockets and Persistent Connections

## 1. Definition

**Plain language:** HTTP was built around a client asking and a server answering, one exchange at a time — great for loading a web page, awkward for something like a chat app or a live stock ticker where the server needs to push new data to the client the instant it's available, without the client having to keep asking "anything new yet?" WebSockets fix this by upgrading a normal HTTP connection into a persistent, full-duplex pipe that either side can send data through, at any time, for as long as the connection stays open.

**Precise definition:** **WebSocket** (RFC 6455) is a protocol providing **full-duplex, bidirectional communication** over a single, long-lived TCP connection, established via an **HTTP Upgrade handshake** — the client sends a normal HTTP/1.1 request with `Connection: Upgrade` and `Upgrade: websocket` headers, and a server that supports WebSockets responds with `101 Switching Protocols`, after which the underlying TCP connection stops speaking HTTP entirely and switches to the WebSocket **framing protocol** — a lightweight binary or text message format with no per-message HTTP header overhead, no request/response pairing requirement, and no inherent limit on which side sends first or how often. Once upgraded, either endpoint can send a **frame** (a discrete message, text or binary) to the other at any time, and the connection remains open until either side explicitly closes it or the underlying TCP connection drops.

> 💡 **Tip:** The defining shift WebSockets make isn't "faster HTTP" — it's abandoning the request/response model entirely after the initial handshake. Once upgraded, there is no more "request" or "response"; there are just messages flowing in either direction whenever either side has something to send. Reasoning about a WebSocket connection with HTTP's request/response mental model ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) is the single most common source of confusion when first working with it.

## 2. Why This Matters

- **WebSockets are the standard mechanism behind every "live" feature in modern applications** — chat, live notifications, collaborative editing, real-time dashboards, and trading/market-data feeds all rely on this persistent-connection model rather than repeated HTTP polling.
- **Load balancer and reverse proxy configuration for WebSockets is meaningfully different from ordinary HTTP configuration**, and a very common production issue is a proxy or load balancer that doesn't correctly forward the `Upgrade`/`Connection` headers or that applies an HTTP-appropriate idle timeout to what should be a long-lived connection.
- **WebSockets change capacity planning assumptions** — a service that used to handle brief, stateless HTTP requests now holds open, potentially very long-lived TCP connections per client, which has real implications for connection limits, memory per connection, and horizontal scaling/load-balancing strategy ([§77](../Part9/Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md), sticky sessions, in Part 9).
- **Understanding the upgrade handshake is necessary to debug why a WebSocket connection fails to establish at all** — a failure at this stage looks like an ordinary HTTP error and is easy to misdiagnose without understanding what should have happened instead.
- **Firewalls, corporate proxies, and some older network appliances historically mishandle or block the WebSocket upgrade**, since it doesn't fit a purely request/response HTTP traffic model — this is a real, still-encountered connectivity issue for certain client networks.

## 3. Prerequisites and Dependencies

This section directly builds on [§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)'s HTTP/1.1 request/response fundamentals, since the WebSocket handshake is itself a normal HTTP request/response exchange (using the `Upgrade` mechanism defined in HTTP) before the connection transitions to WebSocket framing — understanding [§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md) thoroughly is necessary to recognize exactly where the handshake ends and WebSocket-native communication begins. The TCP connection model from Part 7 ([§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)), particularly the concept of a long-lived connection and how TCP keepalive/idle-timeout behavior works, is directly relevant to this section's coverage of connection lifecycle and proxy timeout issues. [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) (TLS) is relevant background for understanding secure WebSocket connections (`wss://`), which layer the same TLS handshake underneath the WebSocket upgrade exactly as HTTPS does for HTTP.

## 4. Architecture / Conceptual Diagram

```text
   CLIENT                                                     SERVER

   1. Normal TCP connection + TLS handshake if wss:// (§55, §65)
              │
   2. HTTP UPGRADE HANDSHAKE (still ordinary HTTP at this point):

      GET /chat HTTP/1.1
      Host: app.example.com
      Upgrade: websocket
      Connection: Upgrade
      Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
      Sec-WebSocket-Version: 13
      ─────────────────────────────────────────────────────►
                                                    ◄───────── HTTP/1.1 101 Switching Protocols
                                                                Upgrade: websocket
                                                                Connection: Upgrade
                                                                Sec-WebSocket-Accept: s3pPLMBi...

   3. CONNECTION IS NOW A WEBSOCKET — no more HTTP request/
      response pairing; the SAME underlying TCP connection now
      carries WebSocket frames, either direction, any time:

      Client ──► {"type":"chat","text":"hi"}    (frame, client►server)
                                            ◄── {"type":"chat","text":"hey"}   (frame, server►client,
                                                                                 unprompted — no request
                                                                                 needed for the server
                                                                                 to send this)
      Client ──► {"type":"typing"}
                                            ◄── {"type":"presence","online":42}
      (connection stays open, both sides send at will,
       until either side sends a close frame or the
       TCP connection drops)
```

- **`Sec-WebSocket-Key` and `Sec-WebSocket-Accept` are a lightweight handshake-confirmation mechanism**, not encryption — the server transforms the client's key using a fixed algorithm (defined in RFC 6455) and returns the result, proving the response is a genuine WebSocket-aware server responding to this specific handshake rather than, say, a misconfigured proxy or cache accidentally returning a cached `101` response.
- **The `101 Switching Protocols` status code is the pivot point** — everything before it is ordinary HTTP/1.1 ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) that any HTTP-aware intermediary understands; everything after it is WebSocket framing that a plain HTTP-only intermediary cannot meaningfully interpret, which is exactly why WebSocket-unaware proxies frequently mishandle connections past this point.
- **There is no request/response pairing after the upgrade** — a server can send ten messages before the client sends one, or vice versa; this genuinely un-does one of HTTP's core structural assumptions and is why WebSocket application logic and HTTP application logic are usually built with different frameworks/patterns even within the same service.

## 5. Hands-On

### 5.1 Observing the Upgrade Handshake with `curl`

**Purpose:** See the literal HTTP-level handshake that precedes every WebSocket connection, using an ordinary HTTP tool.

**Syntax:**

```bash
curl -v -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: <base64-key>" <url>
```

**Example usage and expected output:**

```bash
$ curl -v -N \
    -H "Connection: Upgrade" -H "Upgrade: websocket" \
    -H "Sec-WebSocket-Version: 13" \
    -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
    http://echo.example.com/ws
> GET /ws HTTP/1.1
> Host: echo.example.com
> Upgrade: websocket
> Connection: Upgrade
> Sec-WebSocket-Version: 13
> Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
>
< HTTP/1.1 101 Switching Protocols
< Upgrade: websocket
< Connection: Upgrade
< Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

- `curl` demonstrates that a WebSocket connection literally begins as a normal, inspectable HTTP request — every technique from [§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)'s Hands-On section (reading request/response headers, checking the status line) applies directly to diagnosing handshake failures.
- Past the `101` response, `curl -N` (disabling output buffering) would show raw WebSocket frame bytes rather than further readable HTTP — `curl` isn't a WebSocket client and can't meaningfully continue the conversation, but confirming the handshake itself succeeded is often exactly what's needed to isolate a connectivity problem to "before the upgrade" versus "after the upgrade."

**Production usage example:** This exact technique — confirming a `101 Switching Protocols` response is actually returned — is the first diagnostic step whenever a WebSocket-based feature fails to connect in a new environment (a new load balancer, a new corporate network, a new CDN configuration), since it immediately distinguishes "the HTTP-level handshake itself is failing" (a proxy/header/routing problem) from "the handshake succeeds but the WebSocket session behaves wrong afterward" (an application-level problem).

**Common errors:** Assuming a `200 OK` or any status other than exactly `101` means the WebSocket connection is working — a proxy or load balancer that doesn't understand or forward the upgrade correctly will often return an ordinary HTTP response (sometimes even one that looks superficially successful) instead of performing the protocol switch, and application code naively treating that as "connected" will fail confusingly on the first attempted message send.

### 5.2 Testing an Interactive WebSocket Session with `wscat`

**Purpose:** Send and receive actual WebSocket messages interactively, after the handshake described in 5.1 completes, to validate real bidirectional behavior.

**Syntax:**

```bash
wscat -c <ws_url>
```

**Example usage and expected output:**

```bash
$ wscat -c wss://chat.example.com/ws
Connected (press CTRL+C to quit)
> {"type":"join","room":"ops"}
< {"type":"joined","room":"ops","members":3}
< {"type":"chat","user":"alice","text":"deploy is green"}
> {"type":"chat","text":"thanks, confirming on my end"}
< {"type":"chat","user":"bob","text":"nice, closing the ticket"}
```

- Lines prefixed `>` are messages the client (this tool) sent; lines prefixed `<` are messages received — note that messages arrive from the server (`bob`'s and `alice`'s chat messages) with no corresponding client request immediately preceding them, directly demonstrating the unprompted, server-initiated push behavior that distinguishes this from ordinary HTTP request/response.
- The connection stays open across the entire interactive session — this single TCP connection (upgraded via the handshake in 5.1) is carrying every message shown, in both directions, without re-establishing anything between messages.

**Production usage example:** `wscat` (or browser developer tools' Network tab WS filter, which shows the same frame-by-frame message log for a page's active WebSocket connections) is the standard tool for manually validating a WebSocket API's message contract during development and for reproducing customer-reported real-time feature issues outside of the full application UI.

**Common errors:** Testing a WebSocket endpoint that requires authentication (commonly via a token in the initial upgrade request's headers or query string, since WebSocket connections can't send custom headers with every message the way HTTP requests can) without including that token, producing a connection that appears to establish (a `101` succeeds) but is then immediately closed by the server-side application logic — this can look identical to a handshake failure without checking the specific close code/reason the server sends.

## 6. Production Usage Notes

- **Load balancers and reverse proxies must be explicitly configured to support the WebSocket upgrade** — many default configurations apply HTTP-appropriate short idle timeouts that will silently kill a long-lived, otherwise-idle WebSocket connection, and some older proxy configurations don't forward the `Upgrade`/`Connection` headers correctly at all, both of which need deliberate configuration rather than assuming default HTTP proxying "just works" for WebSockets.
- **Horizontal scaling of WebSocket-backed services requires session-awareness that stateless HTTP request handling doesn't need** — because a client stays connected to one specific backend server instance for the life of the connection, broadcasting a message to "all connected clients" across a scaled-out fleet typically requires a separate pub/sub or message-broker layer to fan the message out to whichever backend instance actually holds each client's connection.
- **Connection count, not request rate, becomes the primary capacity metric for a WebSocket-heavy service** — a service handling 10,000 concurrent, mostly-idle WebSocket connections has very different resource needs (mostly memory and file descriptors held open) than a service handling 10,000 requests per second of ordinary HTTP traffic, and capacity planning needs to reflect that distinction explicitly.

## 7. Security Considerations

- **WebSocket connections do not automatically inherit the same-origin protections browsers apply to ordinary HTTP requests in all the ways developers might assume** — a WebSocket server must explicitly validate the `Origin` header during the handshake if it wants to restrict which web pages are allowed to open connections to it, since the browser itself does not block cross-origin WebSocket connection attempts the way it restricts certain cross-origin HTTP requests.
- **Authentication for WebSockets requires deliberate design**, since the ongoing connection has no per-message equivalent of an HTTP `Authorization` header — common patterns include a token passed during the initial upgrade request (as a header, if the client library supports it, or as a query parameter) or an explicit authentication message sent as the first frame after connecting, and either approach needs the server to validate it before treating the connection as authenticated.
- **A long-lived, authenticated WebSocket connection represents a longer-lived security exposure window than a single short HTTP request** — if a session token used to authenticate the connection is later revoked, a naive implementation that only checks authentication at connect time won't notice, so production systems typically need an explicit mechanism to forcibly close connections tied to a revoked session.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                   | Resolution Path                                                                                                    |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| WebSocket connection fails to establish, client reports a generic connection error | The load balancer/proxy isn't forwarding the `Upgrade`/`Connection` headers, or returns something other than `101` | Confirm with `curl -v` (5.1) exactly what status code and headers come back; fix proxy configuration to support the upgrade explicitly |
| Connections drop after a consistent, short period of inactivity | A proxy or load balancer's HTTP-appropriate idle timeout is closing the "idle" WebSocket connection | Configure a longer idle timeout specifically for WebSocket traffic, or implement application-level ping/pong keepalive frames |
| Messages broadcast to "all users" only reach some connected clients in a scaled-out deployment | Each backend instance only knows about the WebSocket connections it personally holds; there's no fan-out mechanism across instances | Introduce a pub/sub layer (message broker) so a broadcast reaches every backend instance, which then forwards to its own locally-held connections |
| Connection establishes (`101` succeeds) but immediately closes | Application-level authentication/authorization rejected the connection after the protocol-level handshake already succeeded | Check the WebSocket close code/reason sent by the server, not just the initial handshake status, to find the actual rejection reason |

## 9. Best Practices

- Explicitly configure load balancers and reverse proxies for WebSocket support — correct header forwarding and an appropriately long (or ping/pong-driven) idle timeout — rather than assuming default HTTP proxy behavior is sufficient.
- Validate the `Origin` header server-side for any WebSocket endpoint that should be restricted to specific web origins, since browsers do not enforce this restriction on WebSocket connections automatically.
- Design explicit authentication and session-revocation handling for WebSocket connections from the start, since the "check auth once at connect time and never again" default is a real, easily-overlooked security gap for long-lived connections.

## 10. Common Anti-Patterns / Mistakes

- **Assuming a WebSocket connection, once authenticated, remains valid for its entire lifetime with no further checks** — a revoked session or expired permission should be able to forcibly terminate an already-open connection, which requires deliberate design most teams don't build in until it's needed reactively.
- **Deploying WebSocket-backed services behind load balancers without adjusting idle timeout or header-forwarding configuration**, leading to mysterious, intermittent disconnects that get misattributed to application bugs rather than the actual infrastructure-layer cause.
- **Building "broadcast to all clients" logic that only accounts for connections held by the single backend instance handling the request**, silently failing to reach clients connected to other instances in a scaled-out deployment, without a pub/sub or broker layer to fan out across instances.

## 11. Interview Questions

**🎯 Beginner:** _"How does a WebSocket connection get established, given that it starts as an HTTP request?"_
**Model answer:** The client sends a normal HTTP/1.1 request including `Upgrade: websocket` and `Connection: Upgrade` headers, along with a `Sec-WebSocket-Key`. If the server supports WebSockets, it responds with `101 Switching Protocols` and a `Sec-WebSocket-Accept` header derived from the client's key. At that point, the same underlying TCP connection stops being used for HTTP and starts carrying WebSocket frames instead — the initial exchange is ordinary HTTP, and the `101` response is the signal that the protocol has switched.
_What the interviewer is probing for:_ Understanding that WebSockets bootstrap off HTTP rather than being a completely separate, unrelated protocol from the start.

**🎯 Intermediate:** _"Why can't you just use repeated HTTP polling instead of WebSockets for something like a live chat feature?"_
**Model answer:** You can, and many systems did before WebSockets were standardized, but it has real costs: every poll is a full new HTTP request (potentially a new TCP/TLS handshake if connections aren't reused efficiently, [§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)), carrying full header overhead, and there's an inherent trade-off between polling frequency (more requests, more server load, more wasted "nothing changed" responses) and latency (less frequent polling means new messages take longer to appear). WebSockets solve this by keeping one connection open and letting the server push a message the instant it's ready, with no polling overhead and no artificial latency floor — the server sends when it has something to send, not on the client's polling schedule.
_What the interviewer is probing for:_ Whether the candidate understands the actual trade-off WebSockets solve (latency vs. overhead) rather than just "WebSockets are the modern way to do real-time."

**🎯 Senior:** _"Your team's WebSocket-based notification service works fine locally but users behind a corporate load balancer report random disconnects every few minutes. What's your diagnosis approach?"_
**Model answer:** This is a very characteristic symptom of a proxy or load balancer applying an HTTP-appropriate idle timeout to what should be treated as a long-lived connection — many load balancers default to relatively short idle timeouts (30-60 seconds is common) tuned for typical HTTP request/response patterns, and a WebSocket connection with no application traffic for that period looks "idle" to the proxy even though it's a perfectly healthy, intentionally persistent connection. I'd check the load balancer's specific idle/keepalive timeout configuration first, and separately implement application-level ping/pong frames sent at an interval shorter than that timeout, both to keep the connection demonstrably active from the proxy's perspective and to let the application itself detect and clean up genuinely dead connections rather than relying solely on TCP-level failure detection, which can be slow.
_What the interviewer is probing for:_ Recognition of the idle-timeout mismatch as the leading real-world cause of this exact symptom, and knowledge of ping/pong as the standard mitigation, not just guessing at network issues generically.

**🎯 Architect:** _"You're designing a real-time collaborative editing feature that needs to scale to hundreds of thousands of concurrent WebSocket connections across many backend instances. What architectural components do you need beyond just accepting WebSocket connections?"_
**Model answer:** Beyond the WebSocket-accepting service layer itself, I'd need a pub/sub or message-broker layer (something like Redis pub/sub, Kafka, or a dedicated real-time messaging backbone) so that when one user's edit needs to reach every other collaborator on the same document, regardless of which backend instance holds each of their individual WebSocket connections, the message can fan out correctly across instances rather than only reaching clients connected to the same instance that received the edit. I'd design connection routing/affinity carefully at the load balancer layer, since a WebSocket client needs to stay connected to one specific backend instance for the life of its connection (unlike stateless HTTP requests that can be load-balanced per-request). I'd build explicit health/liveness detection using ping/pong frames rather than relying purely on TCP-level failure detection, since a half-open connection can otherwise consume server resources indefinitely without the server realizing the client is gone. And I'd plan capacity around concurrent connection count and per-connection memory footprint as the primary scaling metric, not request-per-second throughput, since that's the resource profile that actually governs how many WebSocket clients a given instance can hold open simultaneously.
_What the interviewer is probing for:_ Whether the candidate can reason about the genuinely different architectural requirements of a stateful, connection-oriented system at scale, beyond simply "WebSockets work for one user, so it'll work for many."

## 12. Common Misconceptions

1. **"WebSockets are just a faster version of HTTP requests."** They abandon the request/response model entirely after the handshake — messages flow in either direction at any time, with no pairing requirement, which is a structural difference, not just a performance improvement.
2. **"A WebSocket connection is automatically secure just because the initial handshake used HTTPS/`wss://`."** TLS on the underlying connection protects data in transit, but authentication, authorization, and origin validation for the WebSocket session itself are separate concerns the application must handle explicitly.
3. **"Load balancers handle WebSocket connections the same way they handle ordinary HTTP requests, with no special configuration needed."** WebSocket connections are long-lived and don't fit the short request/response pattern most load balancer defaults (especially idle timeouts) are tuned for, and typically need explicit configuration.
4. **"Once a WebSocket connection authenticates successfully, that authentication remains valid until the connection naturally closes."** Without deliberate design, a long-lived connection has no built-in mechanism to notice a mid-session permission or session revocation — this has to be built explicitly.

## 13. 🔑 Key Takeaways

- A WebSocket connection begins as an ordinary HTTP request with `Upgrade`/`Connection` headers, and a `101 Switching Protocols` response marks the point where the same TCP connection switches from HTTP to WebSocket framing.
- After the upgrade, there is no more request/response pairing — either side can send a message at any time, which is the core structural shift WebSockets make over HTTP's model ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)).
- Load balancers and proxies need explicit configuration (header forwarding, appropriately long idle timeouts or ping/pong support) to correctly support WebSocket traffic, since default HTTP-tuned behavior often silently breaks long-lived connections.
- Scaling WebSocket-backed services requires connection-count-based capacity planning and typically a pub/sub/broker layer for cross-instance broadcast, since each client stays pinned to one specific backend instance for the life of its connection.
- Authentication, origin validation, and session-revocation handling for WebSockets require deliberate application-level design, since the protocol has no built-in equivalent of HTTP's per-request `Authorization` header re-validated on every request.

## 14. Related Concepts & What's Next

[§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md) is the direct foundation for this section, since the WebSocket handshake is itself an HTTP request/response exchange using the `Upgrade` mechanism, and understanding it thoroughly is what makes the handshake diagram in this section legible. [§77](../Part9/Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md) (Part 9) covers session persistence/sticky sessions in load balancing, directly relevant to the connection-affinity requirement this section's Architect answer describes for WebSocket-backed services at scale. [§71](Section-71-Part8-gRPC-and-Modern-RPC-Protocol-Concepts.md) continues this Part into gRPC, a different but conceptually related shift away from classic request/response HTTP semantics, using HTTP/2's streaming capabilities ([§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) rather than an upgrade-based protocol switch, worth contrasting directly against WebSockets' approach.

**Next Section:** [§71](Section-71-Part8-gRPC-and-Modern-RPC-Protocol-Concepts.md) — `Section-71-Part8-gRPC-and-Modern-RPC-Protocol-Concepts.md`
