# Section 12 (Part 2): Protocol Data Flow: A Packet's Journey From Application to Wire

## 1. Definition

**Plain language:** This section takes everything covered so far — layers, encapsulation, PDUs — and walks through one complete, realistic example from start to finish: what actually happens, step by step, when you type a URL into a browser (or run `curl`) until a response comes back, tying every layer and every header to a concrete, observable action.

**Precise definition:** **Protocol data flow** describes the complete, ordered sequence of operations across every layer of the network stack required to satisfy a single application-level request — from the initiating application resolving a name (DNS), through connection establishment (TCP's three-way handshake), through securing the channel (TLS handshake), through the actual application-layer exchange (an HTTP request/response), and finally through connection teardown — with each stage involving its own round of encapsulation ([§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md)) and its own PDU ([§11](Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md)) at the layer it operates on. Understanding this flow as a single continuous, ordered sequence — rather than as isolated, disconnected facts about DNS, or TCP, or HTTP — is what turns the layered model from abstract theory into a genuine diagnostic tool: a stalled request can be pinpointed to the exact stage in this sequence where it stopped progressing.

> 💡 **Tip:** Every stage in this journey is individually observable with an ordinary command. `dig`/`nslookup` for DNS, `tcpdump`/`ss` for the TCP handshake, `openssl s_client` or `curl -v`'s own TLS output for the TLS handshake, and `curl -v`'s response headers for the final HTTP exchange. If you can run all of these commands against a real target and correctly narrate what each stage is doing and why it comes before the next, you have genuinely internalized this section, not just memorized its diagram.

## 2. Why This Matters

- **This is the actual sequence behind "the website is slow" or "the API times out."** Every real-world connectivity or latency investigation is, at its core, figuring out which stage of this exact sequence is taking too long or failing outright.
- **Explains why DNS problems look like "the whole internet is down."** If DNS resolution (the very first stage) fails, nothing downstream — TCP, TLS, HTTP — ever gets a chance to run at all, which is why DNS outages are disproportionately disruptive relative to how "small" the DNS component seems.
- **Clarifies where time actually goes in a request.** Modern browsers' network tabs and APM tools break request timing down into exactly these stages (DNS lookup time, connection time, TLS negotiation time, time to first byte) — understanding the underlying protocol flow is what makes those timing breakdowns interpretable rather than opaque numbers.
- **Directly informs performance optimization decisions.** Techniques like DNS prefetching, TCP connection reuse/keep-alive, TLS session resumption, and HTTP/2 multiplexing ([§64](../Part8/Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) each target eliminating or amortizing the cost of one specific stage in this sequence — knowing the sequence is a prerequisite to understanding why each optimization exists.
- **A foundational, near-universal interview scenario.** "Walk me through what happens when you type a URL into a browser and press enter" is one of the most common systems/networking interview questions across the entire industry, precisely because answering it well requires demonstrating fluency across the entire stack.

## 3. Prerequisites and Dependencies

This section is a synthesis of [§8](Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md) (OSI layers), [§9](Section-09-Part2-The-TCP-IP-4-Layer-Model-and-How-It-Maps-to-OSI.md) (TCP/IP layers), [§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md) (encapsulation), and [§11](Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md) (PDU naming) — all four are used together here in one continuous worked example, so at least a working familiarity with each is assumed. It intentionally previews concepts covered in full depth much later: DNS resolution ([§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)–[§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md), Part 6), the TCP three-way handshake ([§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md), Part 7), and TLS's handshake ([§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md), Part 8) are all introduced here only to the depth needed to place them correctly in the overall sequence — the mechanics of each are deferred to their dedicated sections. [§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md) immediately follows and turns this same sequence into an explicit troubleshooting checklist.

## 4. Architecture / Conceptual Diagram

```text
   THE JOURNEY: curl https://example.com/  (or a browser loading a page)

   Stage 1 — DNS RESOLUTION (Application-layer query, over UDP/TCP port 53)
   ┌──────────┐  "what's the IP for example.com?"   ┌──────────────┐
   │  client  │ ───────────────────────────────────► │ DNS resolver │
   │          │ ◄─────────────────────────────────── │              │
   └──────────┘         "93.184.216.34"               └──────────────┘
        │
        ▼
   Stage 2 — TCP THREE-WAY HANDSHAKE (Transport layer, establishes the connection)
   ┌──────────┐  SYN ─────────────────────────────►  ┌──────────────┐
   │  client  │  ◄───────────────────────── SYN-ACK   │ 93.184.216.34│
   │          │  ACK ─────────────────────────────►   │   port 443   │
   └──────────┘                                       └──────────────┘
        │              connection now ESTABLISHED
        ▼
   Stage 3 — TLS HANDSHAKE (secures the now-established TCP connection)
   ┌──────────┐  ClientHello ─────────────────────►   ┌──────────────┐
   │  client  │  ◄───────────── ServerHello, cert      │ 93.184.216.34│
   │          │  key exchange, Finished ──────────►    │   port 443   │
   └──────────┘  ◄───────────────────────── Finished   └──────────────┘
        │           encrypted channel now established
        ▼
   Stage 4 — HTTP REQUEST/RESPONSE (Application-layer exchange, inside the TLS tunnel)
   ┌──────────┐  GET / HTTP/1.1 ──────────────────►   ┌──────────────┐
   │  client  │  Host: example.com                     │ 93.184.216.34│
   │          │  ◄───────────────── HTTP/1.1 200 OK    │   port 443   │
   └──────────┘       <html>...</html>                 └──────────────┘
        │
        ▼
   Stage 5 — CONNECTION REUSE OR TEARDOWN (FIN/ACK, or kept alive for reuse)

   Each ─────► arrow above is itself a full encapsulation trip:
   Application data → Segment (TCP) → Packet (IP) → Frame (Ethernet) → Bits
   ...traveling down the sender's stack, across the wire, and back up the
   receiver's stack (de-encapsulation) — repeated for every message shown.
```

- **DNS resolution happens first and is a prerequisite for everything else** — without an IP address, there is nothing to open a TCP connection to; this is why DNS failures present as total unreachability rather than a partial degradation.
- **TCP's three-way handshake must fully complete before any application data (including the TLS handshake itself) can be sent** — TLS negotiation happens *inside* an already-established TCP connection, not in parallel with establishing it (TCP Fast Open and QUIC, [§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md), are notable exceptions that blur this ordering for performance).
- **TLS's handshake must complete before the HTTP request is sent** (for HTTPS) — the "encrypted channel" isn't optional middleware; the actual HTTP GET request in Stage 4 is only ever sent once the TLS handshake in Stage 3 has produced usable session keys.
- **Every arrow in this diagram is, underneath, the full encapsulation/de-encapsulation cycle from [§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md)** repeated for that specific message — the DNS query, each TCP handshake segment, each TLS handshake message, and the final HTTP request/response are all independently wrapped in their own Transport/Internet/Data-Link headers for their trip across the wire.

## 5. Hands-On

### 5.1 Observing Each Stage Independently, in Sequence

**Purpose:** Run one command per stage of the journey above, confirming each stage completes before manually moving to the next — making the sequential dependency between stages concrete rather than theoretical.

**Syntax:**

```bash
dig +short example.com                              # Stage 1: DNS
sudo tcpdump -i any -c 6 'host example.com and tcp'  # Stage 2/3: capture the handshakes
curl -v https://example.com/ 2>&1 | head -30         # Stages 1-4 all at once, annotated
```

**Example usage and expected output:**

```bash
$ dig +short example.com
93.184.216.34

$ curl -v https://example.com/ 2>&1 | head -30
*   Trying 93.184.216.34:443...
* Connected to example.com (93.184.216.34) port 443 (#0)
* ALPN: curl offers h2,http/1.1
* TLS handshake, Client hello (1):
* TLS handshake, Server hello (2):
* TLS handshake, Certificate (11):
* TLS handshake, Server key exchange (12):
* TLS handshake, Server finished (14):
* TLS handshake, Client key exchange (16):
* TLS handshake, Finished (20):
* SSL connection using TLSv1.3 / TLS_AES_128_GCM_SHA256
* ALPN: server accepted h2
> GET / HTTP/2
> Host: example.com
> user-agent: curl/8.4.0
> accept: */*
>
< HTTP/2 200
< content-type: text/html
```

- `dig +short` isolates Stage 1 (DNS) in complete isolation, confirming resolution succeeds before anything else is attempted.
- `curl -v`'s output is annotated in a way that maps almost line-for-line onto the diagram's stages: `Trying ... Connected` is Stage 2 (TCP handshake succeeded), the `TLS handshake` lines are Stage 3, and the `> GET` / `< HTTP/2 200` exchange is Stage 4.

**Production usage example:** This exact `curl -v` output format is the single most common first diagnostic artifact attached to a "can't reach the API" support ticket or incident, precisely because it self-documents which stage of the journey succeeded last before things went wrong.

**Common errors:** Engineers sometimes see the TLS handshake lines and conclude TLS is "part of the problem" even when the actual failure is later, in the Stage 4 HTTP exchange — reading the output in strict top-to-bottom sequence order, matching it against the stages above, avoids this misattribution.

### 5.2 Isolating a Stalled Request to a Specific Stage With `curl`'s Timing Breakdown

**Purpose:** Use `curl`'s built-in timing variables to quantify exactly how long each stage of the journey took, turning the qualitative sequence into hard, comparable numbers.

**Syntax:**

```bash
curl -w "@format-file" -o /dev/null -s <url>
```

**Example usage and expected output:**

```bash
$ cat format-file
    DNS lookup:    %{time_namelookup}s\n
    TCP connect:   %{time_connect}s\n
    TLS handshake: %{time_appconnect}s\n
    Time to first byte: %{time_starttransfer}s\n
    Total:         %{time_total}s\n

$ curl -w "@format-file" -o /dev/null -s https://example.com/
    DNS lookup:    0.012s
    TCP connect:   0.031s
    TLS handshake: 0.089s
    Time to first byte: 0.142s
    Total:         0.148s
```

- Each of these `curl` timing variables corresponds directly to a *cumulative* checkpoint in the journey diagram: `time_namelookup` is the end of Stage 1, `time_connect` is the end of Stage 2, `time_appconnect` is the end of Stage 3, and `time_starttransfer` is the moment the first byte of the Stage 4 HTTP response arrives.

**Production usage example:** This exact breakdown is how performance engineers determine whether a slow page load is a DNS problem (high `time_namelookup`), a network/routing problem (high `time_connect` relative to `time_namelookup`), a TLS/certificate-chain problem (high `time_appconnect` relative to `time_connect`), or a genuine backend/application slowness problem (a large gap between `time_appconnect` and `time_starttransfer`) — each stage's cost is isolated numerically rather than guessed at.

**Common errors:** Interpreting these values as non-cumulative (i.e., thinking `time_connect: 0.031s` means "TCP connection took 31ms after TLS finished") is a common misread — each `curl` timing variable is measured from the very start of the request, so the actual duration of, say, the TLS handshake stage alone is `time_appconnect - time_connect`, not `time_appconnect` on its own.

## 6. Production Usage Notes

- Modern connection reuse (HTTP keep-alive, and especially HTTP/2's connection multiplexing, [§64](../Part8/Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) exists specifically to avoid repeating Stages 1–3 (DNS, TCP handshake, TLS handshake) for every single request to the same host — once a connection is established and secured, many logical HTTP requests can reuse it, paying the Stage 1–3 cost only once instead of per-request.
- TLS session resumption (session tickets/session IDs) is a targeted optimization specifically at Stage 3, letting a client and server that have previously completed a full TLS handshake skip most of the renegotiation on a subsequent connection — this is why a second visit to the same site is frequently noticeably faster to secure than the first.
- QUIC ([§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) is notable precisely because it restructures this entire sequence — it combines what would be separate TCP-handshake and TLS-handshake round trips (Stages 2 and 3) into a single combined handshake, reducing the number of round trips required before Stage 4 (the actual application data) can begin.

## 7. Security Considerations

- Every stage prior to the TLS handshake (DNS resolution, the TCP handshake itself) happens in plaintext and is visible to anyone observing the path — DNS queries reveal what hostnames a client is resolving (a real privacy consideration, addressed by DNS-over-HTTPS/DNS-over-TLS, briefly touched on in Part 6), and the TCP handshake reveals source/destination IPs and ports even for an otherwise fully encrypted HTTPS session.
- A failure or interception at any stage prior to Stage 4 can compromise everything downstream — a DNS response that's been spoofed (directing the client to a malicious IP before any TLS handshake even begins) is a classic attack vector precisely because it happens at the very first, most trusted-by-default stage of the entire sequence (DNSSEC, [§49](../Part6/Section-49-Part6-DNSSEC-Chain-of-Trust-and-Threat-Model.md), exists to address this).
- Certificate validation, which happens as part of the Stage 3 TLS handshake, is the specific checkpoint where a client verifies it's actually talking to the server it intended to reach (not an on-path attacker) — a misconfigured or bypassed certificate check at this single stage undermines every guarantee the rest of the encrypted journey depends on.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Stage/Cause                                                                                     | Resolution Path                                                                                                  |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Request fails immediately, "could not resolve host"                          | Stage 1 (DNS) failure — resolver unreachable, no record, or resolution timeout                          | `dig`/`nslookup` ([§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md)) against the same hostname and resolver directly to isolate DNS from everything downstream    |
| `curl` hangs at `Trying ...`, never reaches `Connected`                      | Stage 2 (TCP handshake) failure — routing issue, firewall/security group blocking the port, nothing listening | Test the port directly with `nc -zv`/`telnet` ([§117](../Part14/Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md)); check routing ([§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)) and security group/firewall rules        |
| `Connected` succeeds but the request hangs or fails during the TLS lines     | Stage 3 (TLS handshake) failure — certificate mismatch, unsupported cipher/protocol version, clock skew  | `openssl s_client -connect host:443` for a detailed handshake trace; verify certificate chain and supported TLS versions |
| TLS handshake succeeds, but the HTTP response is slow, wrong, or an error    | Stage 4 (Application layer) issue — backend slowness, application bug, incorrect routing at the app layer | Check application/server-side logs and behavior directly; the transport and security layers have already succeeded, ruling them out |

## 9. Best Practices

- When investigating a "slow" or "broken" request, always determine *which stage* of this sequence is actually implicated (using `curl`'s timing breakdown, 5.2) before speculating about root cause — this alone eliminates the large majority of wasted, undirected debugging effort.
- Design applications and infrastructure to minimize how often Stages 1–3 have to repeat: use connection pooling/keep-alive, favor HTTP/2 or QUIC where available, and ensure DNS TTLs ([§47](../Part6/Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md)) are tuned appropriately rather than defaulting to either extreme (too short causes excessive re-resolution; too long delays legitimate DNS changes from propagating).
- Practice narrating this exact sequence end to end (DNS → TCP handshake → TLS handshake → HTTP exchange → teardown/reuse) fluently, since it is both a genuinely common interview question and the actual mental checklist used in real incident response.

## 10. Common Anti-Patterns / Mistakes

- **Debugging "in the middle" of the sequence without first confirming earlier stages succeeded.** Investigating apparent HTTP-level (Stage 4) errors when the actual failure is that DNS (Stage 1) is intermittently resolving to a stale or wrong IP wastes significant time chasing symptoms rather than the actual failing stage.
- **Assuming HTTPS means "no information is visible on the wire" for the whole request.** DNS resolution and the TCP handshake (Stages 1–2) are unencrypted regardless of whether the eventual connection is HTTPS — hostname (via DNS, and via the TLS ClientHello's SNI field) and connection metadata remain observable to anyone on the path.
- **Treating connection establishment (Stages 2–3) as free or instantaneous when reasoning about latency.** For connections that aren't reused, DNS + TCP handshake + TLS handshake can easily account for more round-trip time than the actual HTTP exchange itself, especially over higher-latency (e.g., cross-region or mobile) paths — ignoring this cost when estimating expected request latency leads to unrealistic performance expectations.

## 11. Interview Questions

**🎯 Beginner:** _"Walk me through, at a high level, what happens when you type a URL into a browser and press enter."_
**Model answer:** First, the browser resolves the hostname to an IP address via DNS. Then it establishes a TCP connection to that IP on the appropriate port (typically 443 for HTTPS). If it's HTTPS, a TLS handshake follows, negotiating encryption and verifying the server's certificate. Once that's done, the browser sends an HTTP request over the now-secure connection, the server responds with the requested content (typically an HTML page), and the browser renders it — often triggering additional requests for embedded resources like images, scripts, and stylesheets, each potentially reusing the same connection or opening new ones.
_What the interviewer is probing for:_ Whether the candidate has a coherent, correctly-ordered mental model of the full request lifecycle — this is one of the most common opening questions in networking and systems interviews for exactly this reason.

**🎯 Intermediate:** _"A request to an HTTPS API takes 800ms total. Using `curl`'s timing breakdown, how would you determine which stage is responsible?"_
**Model answer:** I'd run `curl` with `-w` and the timing format variables — `time_namelookup`, `time_connect`, `time_appconnect`, and `time_starttransfer` — against the same endpoint. Since these are cumulative from request start, I'd compute each stage's individual cost by subtracting consecutive values: DNS cost is `time_namelookup` itself, TCP handshake cost is `time_connect - time_namelookup`, TLS handshake cost is `time_appconnect - time_connect`, and server processing/time-to-first-byte cost is `time_starttransfer - time_appconnect`. Whichever segment accounts for the largest share of the 800ms total points directly to which stage needs further investigation — a large TLS handshake cost might mean an oversized certificate chain or a slow OCSP check, while a large final segment points to backend/application slowness rather than anything networking-related.
_What the interviewer is probing for:_ Practical fluency with a real diagnostic tool and the ability to correctly interpret cumulative timing data, not just knowledge that the stages exist.

**🎯 Senior:** _"Why can a DNS outage make an entire, otherwise perfectly healthy application appear completely down, even though DNS is 'just' name resolution?"_
**Model answer:** Because DNS resolution is Stage 1 of the sequence and every subsequent stage is strictly dependent on it completing successfully — without a resolved IP address, the client has no destination to even attempt a TCP handshake against, so nothing downstream (TCP, TLS, HTTP) ever gets a chance to succeed or fail on its own merits. This creates a disproportionate blast radius: a genuinely small, single-component failure (one DNS resolver, or one authoritative nameserver, misbehaving) presents identically to a total, complete outage from the client's perspective, because the entire rest of the otherwise-healthy stack downstream is never even reached. This is also why DNS caching and TTLs ([§47](../Part6/Section-47-Part6-DNS-Caching-TTLs-and-Negative-Caching.md)) are a deliberate resilience mechanism — a client with a cached, still-valid DNS answer can continue reaching the service even during a DNS-resolution-layer outage, as long as the underlying IP itself is still valid and reachable.
_What the interviewer is probing for:_ Understanding that the sequence is strictly ordered and dependent, not just a list of independent components — and connecting that to why DNS specifically has an outsized failure impact relative to its apparent simplicity.

**🎯 Architect:** _"You're designing a global, latency-sensitive API platform. Using the protocol data flow model, identify the specific optimization opportunities at each stage and justify their priority."_
**Model answer:** Working through the sequence in order: at Stage 1 (DNS), I'd use a low-latency, geographically distributed DNS provider with sensible TTLs, and consider GeoDNS/latency-based routing ([§52](../Part6/Section-52-Part6-DNS-Based-Load-Balancing-and-Failover-Patterns.md)) so clients resolve to the nearest healthy endpoint rather than a fixed one. At Stage 2 (TCP handshake), I'd terminate connections as close to the client as possible — using anycast or a global edge/CDN layer — since each additional millisecond of round-trip time before the connection even establishes is pure overhead multiplied by however many round trips the subsequent stages need. At Stage 3 (TLS), I'd enable TLS session resumption and prefer TLS 1.3 (which reduces the handshake to effectively one round trip versus TLS 1.2's two) to minimize the security-negotiation cost, and would seriously evaluate QUIC/HTTP-3 ([§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md), [§64](../Part8/Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) specifically because it collapses the separate TCP-then-TLS round trips into one combined handshake. At Stage 4 (application), I'd prioritize connection reuse via HTTP/2 multiplexing so that the amortized cost of Stages 1–3 is paid once per client session rather than once per request, and would ensure backend response time itself (the actual time-to-first-byte cost) is monitored and optimized independently, since no amount of transport-layer optimization compensates for genuine backend slowness. I'd prioritize these roughly in the order listed, since each earlier stage's latency is paid by every request regardless of how well later stages are optimized — fixing Stage 1 latency benefits literally every subsequent request, while a Stage 4 optimization benefits only that specific request path.
_What the interviewer is probing for:_ The ability to use the full protocol data flow model as an actual systems-design optimization framework, prioritizing correctly based on where in the sequence latency compounds versus where it's isolated.

## 12. Common Misconceptions

1. **"TLS negotiation happens in parallel with the TCP handshake, so they're roughly the same cost."** TLS negotiation happens strictly after the TCP handshake fully completes (with the notable exception of newer mechanisms like TCP Fast Open and QUIC, which deliberately restructure this) — treating them as parallel, simultaneous costs underestimates total connection-establishment latency.
2. **"HTTPS means the entire request is invisible to anyone on the path."** DNS resolution and the TCP handshake occur before encryption is established and remain visible in plaintext; even the TLS ClientHello itself typically includes the hostname in plaintext (via the SNI extension) unless Encrypted Client Hello is specifically in use.
3. **"A slow request is always a backend/application problem."** A meaningful and often underestimated share of end-to-end request latency, particularly for non-reused connections over longer network paths, comes from DNS, TCP handshake, and TLS handshake costs — stages that have nothing to do with backend application code at all.
4. **"DNS is a minor, low-risk component of the request path."** Because every subsequent stage strictly depends on DNS succeeding first, DNS failures have an outsized, often total, impact on availability relative to how architecturally "small" the DNS component is compared to the rest of the stack.

## 13. 🔑 Key Takeaways

- A single application request is actually a strict, ordered sequence: DNS resolution, then TCP handshake, then (for HTTPS) TLS handshake, then the actual application-layer exchange, then teardown or reuse — each stage depends on the one before it succeeding.
- Every stage in this sequence is individually observable with standard tools (`dig`, `tcpdump`, `openssl s_client`, `curl -v` with timing variables), which makes the sequence a genuine, practical diagnostic checklist rather than abstract theory.
- Because later stages strictly depend on earlier ones, a failure at an early stage (especially DNS) has an outsized impact — the entire rest of an otherwise-healthy system never even gets a chance to run.
- Connection reuse, TLS session resumption, and protocols like QUIC/HTTP-3 all exist specifically to reduce how often the expensive early stages (DNS, TCP handshake, TLS handshake) have to be repeated.
- `curl`'s cumulative timing variables (`time_namelookup`, `time_connect`, `time_appconnect`, `time_starttransfer`) let you convert this qualitative sequence into precise, comparable per-stage latency numbers.

## 14. Related Concepts & What's Next

[§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md) and [§11](Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md) supplied the encapsulation and PDU vocabulary used to describe each stage's underlying wire behavior in this section. [§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md) immediately follows by converting this same sequence into an explicit, actionable troubleshooting checklist. [§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)–[§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md) (Part 6, DNS) and [§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md) (Part 7, TCP's three-way handshake) and [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) (Part 8, TLS handshake) each return to the individual stages introduced here at full depth. [§64](../Part8/Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md) (Part 8) covers HTTP/2 and HTTP/3's specific optimizations to this sequence (multiplexing, QUIC-based combined handshakes) in detail.

**Next Section:** [§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md) — `Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md`
