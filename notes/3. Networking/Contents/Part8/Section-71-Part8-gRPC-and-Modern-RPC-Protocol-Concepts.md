# Section 71 (Part 8): gRPC and Modern RPC Protocol Concepts

## 1. Definition

**Plain language:** Calling a function on a remote machine and having it feel almost like calling a local function — that's the promise of RPC (Remote Procedure Call), and it's been reinvented many times over the decades. gRPC is the current, widely-adopted implementation of that idea: it lets one service call a method on another service over the network using a strict, pre-defined contract, built on top of HTTP/2's streaming capabilities rather than hand-rolled REST-style HTTP endpoints and loosely-typed JSON.

**Precise definition:** **gRPC** is an open-source **RPC (Remote Procedure Call) framework**, originally developed at Google, that defines service methods and message structures in a strongly-typed **Interface Definition Language** — **Protocol Buffers (protobuf)** — compiles that definition into client and server code (**stubs**) in multiple languages, and transports calls over **HTTP/2** ([§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) as the underlying protocol, using its native support for multiplexed streams to implement four call patterns: **unary** (single request, single response — the RPC equivalent of a normal function call), **server streaming** (one request, a stream of responses), **client streaming** (a stream of requests, one response), and **bidirectional streaming** (both sides stream independently over the same call, conceptually similar in spirit to a WebSocket, [§70](Section-70-Part8-WebSockets-and-Persistent-Connections.md), but built on HTTP/2 semantics rather than an upgrade-based protocol switch). Messages are serialized using protobuf's compact **binary wire format**, defined once in a `.proto` file that serves as the strict, versioned **contract** between client and server — a sharp contrast to REST/JSON APIs ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) where the contract is typically informal documentation rather than something a compiler enforces.

> 💡 **Tip:** The single biggest practical difference between gRPC and a typical REST/JSON API isn't performance (though the compact binary format and HTTP/2 multiplexing do help) — it's the contract. A `.proto` file is compiled into generated code for every client and server language involved, so a mismatched field name or type is caught by the compiler at build time, not discovered at runtime when a JSON field silently doesn't parse the way the sender intended. This is why gRPC is heavily favored for internal, service-to-service communication where both ends are under the same organization's control and can regenerate stubs together — and far less common for public-facing APIs where an unknown, uncontrolled client population is calling in.

## 2. Why This Matters

- **gRPC is the dominant choice for internal service-to-service communication in many modern microservice architectures**, particularly in polyglot environments where services in different languages need a fast, strongly-typed way to call each other — understanding it is directly relevant to working with, deploying, and troubleshooting such systems.
- **gRPC's dependency on HTTP/2 has real infrastructure implications** — load balancers, proxies, and network appliances that don't fully support HTTP/2 (particularly its multiplexing and streaming semantics, not just basic HTTP/2 termination) can silently break gRPC traffic in ways that don't affect ordinary REST/JSON traffic over the same infrastructure.
- **The strongly-typed contract model changes how API versioning, backward compatibility, and cross-team coordination work** compared to REST/JSON — protobuf has specific, well-defined rules for what changes are backward-compatible (adding a field) versus breaking (reusing a field number), and understanding those rules is essential for anyone maintaining a gRPC service.
- **Streaming RPC patterns (server, client, and bidirectional streaming) enable use cases that are awkward to build on plain request/response HTTP** — real-time data feeds, large file/data transfer with progress, and long-running bidirectional exchanges are natural fits for gRPC's streaming model.
- **Load balancing gRPC traffic correctly requires different thinking than load balancing ordinary HTTP/1.1 traffic**, since a single long-lived HTTP/2 connection can carry many concurrent gRPC calls multiplexed together ([§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)), meaning naive connection-count-based load balancing can badly imbalance load across backend instances.

## 3. Prerequisites and Dependencies

This section directly depends on [§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)'s coverage of HTTP/2, since gRPC is built entirely on top of HTTP/2's binary framing and stream multiplexing rather than defining its own transport from scratch — understanding streams, multiplexing, and how HTTP/2 differs from HTTP/1.1 ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) is a strict prerequisite for understanding how gRPC's four call patterns actually work at the wire level. [§70](Section-70-Part8-WebSockets-and-Persistent-Connections.md)'s coverage of WebSockets is useful comparative context, since gRPC's bidirectional streaming pattern solves a similar class of problem (both sides sending at will over one connection) using a fundamentally different mechanism (HTTP/2 streams rather than a protocol upgrade), and contrasting the two approaches sharpens understanding of both. No prior familiarity with Protocol Buffers or RPC frameworks generally is assumed — this section introduces those concepts from first principles.

## 4. Architecture / Conceptual Diagram

```text
   .proto FILE (the contract, written once)
   ┌───────────────────────────────────────┐
   │ service UserService {                  │
   │   rpc GetUser(GetUserRequest)           │
   │       returns (UserResponse);           │  ◄── unary
   │   rpc StreamOrders(OrderQuery)          │
   │       returns (stream Order);           │  ◄── server streaming
   │ }                                        │
   │ message GetUserRequest { int32 id = 1; }│
   └────────────────┬────────────────────────┘
                     │ protoc compiler generates
        ┌────────────┴────────────┐
        ▼                          ▼
   CLIENT STUB (generated)    SERVER STUB (generated)
   in language A               in language B
        │                          │
        │   ONE HTTP/2 connection (§64) — multiplexed streams
        ├──────────────────────────────────────────────────►
        │   Stream 1: GetUser call  (unary — 1 req, 1 resp)
        │   Stream 2: StreamOrders call (server streaming —
        │             1 req, MANY resp frames on this stream)
        │   Stream 3: another concurrent unary call
        │   (all interleaved as HTTP/2 frames, on ONE
        │    connection, exactly as described in §64)
        ◄──────────────────────────────────────────────────┤
        │
        │   Protobuf binary wire format for every message —
        │   compact, schema-defined, NOT human-readable JSON

   CALL PATTERNS (all four ride the SAME HTTP/2 stream mechanism):

   Unary:              Client ──req──► Server ──resp──► Client
   Server streaming:   Client ──req──► Server ──resp──► Client
                                        Server ──resp──► Client  (same stream,
                                        Server ──resp──► Client   more frames)
   Client streaming:   Client ──req──► Server
                        Client ──req──► Server
                        Client ──req──► Server ──resp──► Client (one final response)
   Bidi streaming:      Client ──req──► Server
                                        Server ──resp──► Client
                        Client ──req──► Server            (both directions,
                                        Server ──resp──► Client   independently, same stream)
```

- **The `.proto` file is the single source of truth for the API contract**, and the `protoc` compiler generates strongly-typed client and server code from it in every target language — this is what enables the compile-time-checked contract described in the Definition's Tip, versus REST/JSON's typical reliance on informal documentation or a separately-maintained OpenAPI spec that nothing enforces automatically.
- **All four call patterns are really just different usage shapes of a single underlying mechanism: an HTTP/2 stream carrying one or more DATA frames in each direction** — a unary call is simply the simplest case (exactly one request frame set, exactly one response frame set) of the same machinery that server/client/bidirectional streaming use more elaborately.
- **Multiple concurrent gRPC calls between the same client and server typically share one HTTP/2 connection**, multiplexed exactly as described in [§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md) — this is a deliberate design choice for connection efficiency, but it also means load balancing decisions made at connection-establishment time (rather than per-call) can under-utilize backend instances if not accounted for explicitly.

## 5. Hands-On

### 5.1 Inspecting a gRPC Service's Available Methods with `grpcurl`

**Purpose:** Interact with a gRPC service without writing or compiling client code, using reflection to discover its contract at runtime.

**Syntax:**

```bash
grpcurl -plaintext <host>:<port> list
```

**Example usage and expected output:**

```bash
$ grpcurl -plaintext localhost:50051 list
UserService

$ grpcurl -plaintext localhost:50051 list UserService
UserService.GetUser
UserService.StreamOrders

$ grpcurl -plaintext localhost:50051 describe UserService.GetUser
UserService.GetUser is a method:
rpc GetUser ( .GetUserRequest ) returns ( .UserResponse );
```

- This works only if the server has **gRPC server reflection** enabled — without it, `grpcurl` (or any generic tool) has no way to discover the service's methods and message shapes, since unlike REST there's no universally-browsable URL structure to guess at; the `.proto` contract (or reflection standing in for it at runtime) is required.
- `-plaintext` disables TLS for this local test connection — production gRPC services, like production HTTP services, should run over TLS ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) by default, with plaintext reserved for local development.

**Production usage example:** `grpcurl` is the standard ad hoc tool for manually testing or debugging a gRPC service during development or incident response — the direct equivalent of `curl` for REST/JSON APIs ([§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)), letting an engineer make a real gRPC call from the command line without needing the full generated client stub for a specific language.

**Common errors:** Forgetting that most production gRPC services deliberately disable reflection for security reasons (not wanting to expose their full method/message contract to anyone who can reach the port) — `grpcurl list` failing against a production service is very often expected, secure-by-design behavior, not a connectivity problem, and testing against such a service requires the actual `.proto` file supplied explicitly to `grpcurl` instead of relying on reflection.

### 5.2 Making a Unary Call Directly with `grpcurl`

**Purpose:** Demonstrate an actual RPC call and its JSON-represented request/response, showing how gRPC tooling bridges protobuf's binary format to something human-readable for testing.

**Syntax:**

```bash
grpcurl -plaintext -d '<json_payload>' <host>:<port> <Service.Method>
```

**Example usage and expected output:**

```bash
$ grpcurl -plaintext -d '{"id": 42}' localhost:50051 UserService.GetUser
{
  "id": 42,
  "name": "Alice Chen",
  "email": "alice@example.com"
}
```

- The request and response are shown here in JSON purely for human readability in the terminal — on the actual wire, this exact call is serialized using protobuf's compact binary format, not JSON; `grpcurl` handles the JSON-to-protobuf translation using the service's schema (fetched via reflection or supplied explicitly).
- Compare this directly to [§63](Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)'s `curl -X POST` example — the fundamental idea (send a structured request, get a structured response) is the same, but here the method name (`UserService.GetUser`) and field shapes (`id`, `name`, `email`) come from a compiled contract the tooling already knows about, not from documentation the caller has to separately trust is accurate.

**Production usage example:** This exact workflow — calling a specific method with a JSON payload via `grpcurl` — is standard practice for smoke-testing a gRPC service after deployment, reproducing a bug reported against a specific RPC method in isolation, and verifying a service mesh's gRPC routing configuration end-to-end without needing a full client application.

**Common errors:** Supplying a JSON payload with a field name that doesn't match the `.proto` schema (a typo, or a field renamed in a newer contract version) — because the underlying transport is strongly typed, this fails clearly and immediately (an "unknown field" or similar error from `grpcurl`'s JSON-to-protobuf translation step) rather than silently sending malformed or partial data the way a loosely-validated REST/JSON endpoint might.

## 6. Production Usage Notes

- **Load balancing gRPC traffic requires load balancer support for HTTP/2 multiplexing specifically, not just basic HTTP/2 termination** — a load balancer that only balances at the TCP-connection level will send every multiplexed call on a given long-lived connection to the same backend instance, which can badly skew load distribution; gRPC-aware load balancers (or client-side/proxy-based load balancing patterns common in service meshes) balance at the individual-call level instead.
- **Protobuf's field-numbering scheme is the backbone of backward compatibility** — adding a new field with a new field number is safe and ignored by older clients/servers that don't know about it; reusing an old field number for a different purpose, or changing a field's type, breaks compatibility in ways that can be subtle and hard to detect without protobuf-aware tooling checking schema evolution.
- **gRPC's binary format and HTTP/2 dependency make it harder to inspect with generic tools** than REST/JSON traffic — plain `tcpdump`/Wireshark captures ([§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md), [§119](../Part14/Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md), Part 14) show encrypted or binary-framed data rather than readable text, making `grpcurl` and gRPC-aware observability tooling (rather than generic HTTP debugging tools) the practical necessity for troubleshooting.

## 7. Security Considerations

- **gRPC services should run over TLS in any non-local environment**, exactly as HTTPS is the expectation for REST/JSON APIs ([§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)) — `-plaintext` mode is appropriate for local development only, and mutual TLS (mTLS, both client and server presenting certificates) is a common pattern for service-to-service gRPC authentication in zero-trust internal network designs ([§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md), Part 10).
- **Server reflection, while extremely convenient for development and debugging (as shown in 5.1), is a real information-disclosure consideration for production services** — leaving reflection enabled on an internet-facing or otherwise broadly-reachable production gRPC endpoint exposes its complete method and message contract to anyone who can reach the port, and many organizations deliberately disable it outside trusted internal networks.
- **Because gRPC is heavily used for internal service-to-service calls, authentication and authorization between services (not just between end users and a public API) needs explicit design** — a common mistake is assuming "internal network" alone is a sufficient trust boundary, when a proper zero-trust posture ([§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)) treats service-to-service gRPC calls with the same authentication rigor as external API calls.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                     | Resolution Path                                                                                                    |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| gRPC calls fail or hang through a particular load balancer/proxy, but work directly against the backend | The proxy doesn't fully support HTTP/2 multiplexing/streaming, or is downgrading to HTTP/1.1 somewhere in the path | Verify HTTP/2 (not just TLS) is correctly configured end-to-end through every hop; check for proxies known to have incomplete gRPC/HTTP-2 support |
| One backend instance is consistently overloaded while others in the same pool sit idle | Load balancing is happening at the TCP-connection level, and multiple multiplexed calls on one long-lived connection are all landing on the same backend | Use a gRPC-aware or per-call load-balancing strategy instead of connection-count-based balancing |
| A client using an older generated stub gets unexpected/missing data after a server-side schema change | A protobuf field was removed or its field number reused, breaking backward compatibility rather than following additive-only evolution rules | Review the `.proto` change against protobuf's backward-compatibility rules; add new fields with new numbers rather than repurposing old ones |
| `grpcurl list` fails against a specific service but succeeds against others on the same host | That specific service has reflection deliberately disabled (a common, intentional production security practice) | Supply the `.proto` file explicitly to `grpcurl` instead of relying on reflection, or use the service's own documented contract |

## 9. Best Practices

- Treat the `.proto` file as the authoritative, version-controlled contract between services, and follow protobuf's additive-only compatibility rules (new fields get new numbers; never reuse or repurpose an existing field number) when evolving a schema.
- Ensure every load balancer and proxy in a gRPC service's traffic path has genuine, verified HTTP/2 support for multiplexed streaming, not just basic HTTP/2 termination — and prefer gRPC-aware or per-call load balancing over naive connection-count-based balancing.
- Run gRPC services over TLS (mutual TLS for service-to-service authentication where appropriate) by default, and disable server reflection outside trusted development/internal environments.

## 10. Common Anti-Patterns / Mistakes

- **Repurposing an existing protobuf field number for a new, unrelated field** during schema evolution, which silently breaks compatibility with any client or server still running the older schema in ways that can be extremely hard to diagnose after the fact.
- **Assuming "internal service" gRPC traffic doesn't need the same authentication rigor as external API calls**, relying on network location alone as a trust boundary rather than explicit service-to-service authentication (mTLS or token-based).
- **Deploying gRPC services behind load balancers without verifying genuine HTTP/2 multiplexing support**, leading to skewed load distribution or outright connectivity failures that get misattributed to the application rather than the proxy layer.

## 11. Interview Questions

**🎯 Beginner:** _"What is gRPC, and what does it use Protocol Buffers for?"_
**Model answer:** gRPC is an RPC framework that lets one service call methods on another service over the network as if calling a function directly. Protocol Buffers (protobuf) is the interface definition language gRPC uses to define those methods and the structure of the messages they exchange, in a `.proto` file. That file is compiled into strongly-typed client and server code in whatever languages are needed, and it also defines the compact binary format actual messages are serialized into on the wire.
_What the interviewer is probing for:_ Basic understanding that gRPC is a framework built around a schema-first contract, not just "a faster version of REST."

**🎯 Intermediate:** _"Explain the four gRPC call patterns and give a realistic use case for one that isn't a simple unary call."_
**Model answer:** Unary is a single request and a single response, like an ordinary function call. Server streaming is one request that results in a stream of multiple responses over time — for example, subscribing to a live feed of order updates, where the server pushes each new order as it happens rather than the client polling repeatedly. Client streaming is the reverse — the client sends a stream of messages and gets back one final response, useful for something like uploading a large dataset in chunks and getting a single confirmation at the end. Bidirectional streaming lets both sides send messages independently over the same call, useful for something like a real-time collaborative tool where either party might send updates at any time.
_What the interviewer is probing for:_ Whether the candidate understands the practical difference between the patterns and can connect each to a genuine use case, not just recite the four names.

**🎯 Senior:** _"Your team notices that after deploying gRPC services behind a new load balancer, one backend pod is consistently at high CPU while sibling pods are nearly idle, despite the load balancer reporting even connection distribution. What's happening?"_
**Model answer:** This is a classic symptom of connection-level load balancing being applied to a protocol that multiplexes many logically-independent calls over a small number of long-lived connections. If a handful of clients establish long-lived HTTP/2 connections to the service and then make many concurrent gRPC calls multiplexed over those same connections, a load balancer that only distributes at the point of new-connection establishment will send every one of those multiplexed calls to whichever single backend instance handled that original connection — "even connection distribution" says nothing about even call distribution when connections are long-lived and heavily reused. The fix is a gRPC-aware load-balancing approach: either a proxy/load balancer that understands HTTP/2 streams and can distribute at the call level, or a client-side/service-mesh load-balancing pattern where the client itself (or a sidecar) spreads individual calls across multiple backend connections rather than relying on the load balancer's connection-level view.
_What the interviewer is probing for:_ Deep understanding of the interaction between HTTP/2 multiplexing ([§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) and load balancer behavior — a genuinely tricky, realistic production issue that trips up teams new to gRPC at scale.

**🎯 Architect:** _"You're deciding between gRPC and REST/JSON for a new set of internal microservices at a mid-size engineering organization. Walk through the trade-offs you'd weigh."_
**Model answer:** In favor of gRPC: the strongly-typed, compiler-enforced `.proto` contract removes an entire class of integration bugs that REST/JSON's informal-documentation model allows through, which matters more as the number of services and teams grows; the compact binary format and HTTP/2 multiplexing offer real performance benefits for high-volume internal traffic; and native streaming support handles use cases (live feeds, bidirectional exchanges) that are awkward to build cleanly on plain REST. Against gRPC: it requires HTTP/2-aware infrastructure throughout the traffic path (load balancers, proxies, service mesh) which is a real operational dependency to get right, as the load-balancing pitfall above illustrates; it's harder to debug with generic tools since traffic is binary and typically encrypted, requiring gRPC-aware tooling; and it's a poor fit for public-facing APIs consumed by an uncontrolled population of external clients, where REST/JSON's ubiquitous tooling and human-readability are a genuine advantage. Given a mid-size organization building internal, polyglot microservices under one organization's control, I'd lean toward gRPC for internal service-to-service communication specifically, while keeping REST/JSON for any public-facing or externally-consumed API surface, rather than treating the choice as all-or-nothing across the whole platform.
_What the interviewer is probing for:_ Balanced, context-aware architectural judgment — recognizing gRPC's genuine strengths and genuine operational costs rather than treating either technology as universally superior.

## 12. Common Misconceptions

1. **"gRPC is always faster than REST/JSON, in every scenario."** It typically has lower overhead due to binary serialization and HTTP/2 multiplexing, but the difference is often negligible for low-volume traffic, and gRPC's benefits are most pronounced at scale or for latency-sensitive internal service-to-service calls, not universally guaranteed.
2. **"gRPC and REST are interchangeable, so the choice is purely a matter of developer preference."** They differ meaningfully in contract enforcement (compile-time-checked vs. informal documentation), tooling/browsability, and infrastructure requirements (HTTP/2 dependency) — the choice has real downstream consequences, not just style.
3. **"Any load balancer that supports HTTP/2 will load-balance gRPC traffic correctly."** Basic HTTP/2 termination support is not the same as gRPC-aware, per-call load balancing — the multiplexing-related load-skew problem described in this section's Senior interview answer is a real, common gap.
4. **"Adding a field to a protobuf message is always safe, regardless of how it's done."** It's safe only if it uses a genuinely new, previously-unused field number — reusing or repurposing an old field number breaks backward compatibility even though it might look like a harmless addition in a naive schema diff.

## 13. 🔑 Key Takeaways

- gRPC is an RPC framework built on Protocol Buffers (a strongly-typed, compiled contract) and HTTP/2 ([§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) as its transport, supporting unary, server-streaming, client-streaming, and bidirectional-streaming call patterns.
- The strongly-typed `.proto` contract, compiled into generated code for every language involved, is gRPC's central advantage over REST/JSON's typically informal, unenforced API documentation.
- All four gRPC call patterns are different usage shapes of the same underlying mechanism — one or more DATA frames in each direction over an HTTP/2 stream — with unary being the simplest case.
- Load balancing gRPC traffic correctly requires genuine per-call, HTTP/2-multiplexing-aware distribution, since connection-count-based balancing can badly skew load when multiple calls are multiplexed over a small number of long-lived connections.
- Protobuf schema evolution must follow additive-only compatibility rules (new fields get new numbers) to avoid silently breaking clients or servers running an older version of the contract.

## 14. Related Concepts & What's Next

[§64](Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md) is the direct technical foundation for this section, since every gRPC call pattern is implemented using HTTP/2 stream multiplexing — reviewing that section's diagram alongside this one makes the mapping from "gRPC call pattern" to "HTTP/2 stream behavior" concrete. [§70](Section-70-Part8-WebSockets-and-Persistent-Connections.md) offers a useful point of comparison, since WebSockets solve a similar bidirectional-communication problem to gRPC's bidirectional streaming pattern using an entirely different mechanism (an HTTP upgrade to a new framing protocol, rather than native HTTP/2 streams). [§65](Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) and [§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md) (Part 10) are relevant to this section's security coverage of TLS and mutual-TLS-based service-to-service authentication, a very common production pattern for gRPC specifically. This section closes out Part 8's survey of application-layer protocols; Part 9 ([§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md) onward) shifts focus to load balancing, picking up directly on this Part's recurring theme of how HTTP, HTTP/2, WebSocket, and gRPC traffic all need to be distributed correctly across backend instances — [§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md) opens that Part with load balancing fundamentals.

**Next Section:** [§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md) — Part 9, Load Balancing Fundamentals: Why and Where in the Stack
