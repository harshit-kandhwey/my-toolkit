# Section 117 (Part 14): Port and Service Testing: telnet, nc, curl for Network Diagnostics

## 1. Definition

**Plain language:** Once you know a host is reachable at Layer 3 ([§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)), the next question is whether the specific service you actually care about — a database on port 5432, a web server on port 443 — is listening and responding. `telnet`, `nc` (netcat), and `curl` each answer that question with increasing sophistication, from "is anything there" to "does this specific application protocol respond correctly."

**Precise definition:** **`telnet`**, when used as a diagnostic tool rather than a remote-login protocol, opens a raw TCP connection to a specified host and port and reports whether the connection succeeds — a repurposing of an old remote-terminal protocol into the simplest possible port-reachability test. **`nc`** (netcat), often called "the network Swiss Army knife," can open raw TCP or UDP connections, scan port ranges, and act as either a client or a listener, with the `-z` (zero-I/O, scan mode) and `-v` (verbose) flags making `nc -zv <host> <port>` the modern, purpose-built replacement for `telnet`'s connectivity-testing use case. **`curl`** operates at a higher level still — it speaks actual application protocols (HTTP/HTTPS, FTP, and others) natively, so `curl -v` doesn't just confirm a TCP connection but walks through and reports on the full protocol exchange: DNS resolution, TCP handshake, TLS negotiation, and the HTTP request/response cycle, each as a separate, inspectable step.

> 💡 **Tip:** Choose the tool by the layer of the question: `nc -zv` for "is this port even open" (Layer 4), `curl -v` for "does the protocol on that port actually respond correctly" (Layer 5-7). `telnet` is legacy but universally present, so it remains useful specifically on hosts where `nc` isn't installed.

## 2. Why This Matters

- **Port-level testing is the fastest way to distinguish "network problem" from "application problem"** — a port that refuses or times out points at the network/firewall layer; a port that accepts a connection but the application misbehaves points squarely at the application.
- **`curl -v`'s staged output (DNS → TCP → TLS → HTTP) turns a single opaque failure ("it doesn't work") into a specific failing stage**, each of which has a completely different owner and fix (DNS team, network/firewall team, certificate owner, or the application team).
- **These tools require no special privileges** (unlike `tcpdump`, which typically needs root/administrator access), making them usable in restricted production environments and directly by developers without infrastructure access.
- **They are the tools most commonly reached for by application and platform engineers, not just network specialists** — proficiency here is expected of essentially every DevOps and SRE role, not a niche network-team skill.
- **Understanding exactly what "connection refused" vs. "connection timed out" vs. a slow TLS handshake each indicate** removes an enormous amount of guesswork from the most common category of production incident: "the API call is failing."

## 3. Prerequisites and Dependencies

This section assumes the port/socket vocabulary from [§59](../Part7/Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md) (well-known, registered, and ephemeral port ranges) and the common port reference from [§60](../Part7/Section-60-Part7-Common-Port-Reference-22-80-443-53-3306-5432-6379-etc.md), and depends on the TCP handshake/teardown mechanics from [§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md) to correctly interpret what a "connection refused" (RST) versus a hanging connection attempt (silently filtered SYN) actually indicates on the wire. It follows [§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md) in the OSI-layer walk established in [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md), picking up exactly where Layer 3 reachability testing leaves off and moving to Layer 4 (port-level) and Layer 5-7 (protocol-level) testing. `curl`'s TLS-stage output draws on the TLS/SSL handshake concepts from [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md), and its DNS-stage output connects directly to the DNS troubleshooting workflows detailed in [§120](Section-120-Part14-DNS-Troubleshooting-Workflows.md).

## 4. Architecture / Conceptual Diagram

```text
   LAYERED PORT/SERVICE TESTING (increasing protocol awareness)

   nc -zv host port          curl -v https://host/path
   ┌──────────────┐          ┌────────────────────────────────┐
   │ TCP connect   │          │ 1. DNS resolution               │
   │ only — pass/  │          │ 2. TCP handshake  (§55)         │
   │ fail, no      │          │ 3. TLS handshake  (§65)         │
   │ protocol      │          │ 4. HTTP request sent            │
   │ awareness     │          │ 5. HTTP response received       │
   └──────────────┘          │    + status code + headers      │
                              └────────────────────────────────┘

   FAILURE LOCALIZATION BY STAGE

   nc -zv fails            ──►  Layer 4 problem: firewall, SG, no listener
   nc -zv succeeds,
   curl hangs at TLS        ──►  Layer 5 problem: cert issue, TLS version
                                  mismatch, proxy MITM interference
   curl gets TLS but slow
   or wrong HTTP response   ──►  Layer 7 problem: application itself
                                  (misconfigured vhost, backend down,
                                  wrong routing at a reverse proxy)
```

- Each tool answers a strictly narrower or broader question than its neighbors — the layered diagram exists specifically to show that a `curl` failure should be decomposed by *stage*, not treated as one opaque "curl failed" result.
- A raw TCP connection succeeding (`nc -zv` passes) but `curl` failing to complete a TLS handshake is one of the most common and specific signatures in production: it isolates the fault to TLS/certificate configuration or an intercepting proxy, ruling out the network path entirely.
- `curl`'s staged reporting exists because HTTP/HTTPS layers several independent negotiations (DNS, TCP, TLS, HTTP) on top of each other — each stage can fail independently, and `curl -v`'s verbose output labels which stage produced the failure.

## 5. Hands-On

### 5.1 Fast Port Reachability With `nc -zv`

**Purpose:** Confirm whether a specific TCP (or UDP) port is open, closed, or filtered, without needing to speak the actual application protocol.

**Syntax:**

```bash
nc -zv <host> <port>
nc -zvu <host> <port>     # UDP mode
nc -zv <host> <start>-<end>   # port range scan
```

**Example usage and expected output:**

```bash
$ nc -zv db.internal.example.com 5432
Connection to db.internal.example.com 5432 port [tcp/postgresql] succeeded!

$ nc -zv db.internal.example.com 5433
nc: connect to db.internal.example.com port 5433 (tcp) failed: Connection refused

$ nc -zv db.internal.example.com 5434
# hangs, then eventually:
nc: connect to db.internal.example.com port 5434 (tcp) timed out: Operation now in progress
```

**Production usage example:** This exact command is the standard first step when a new application deployment reports "can't connect to the database" — it isolates in seconds whether the problem is network-layer (refused/filtered) or something the application itself is doing wrong once a raw connection clearly succeeds (wrong credentials, wrong database name, application-level misconfiguration).

**Common errors:** Forgetting `-z` and accidentally opening an interactive connection that then appears to hang — `nc` without `-z` tries to hold the connection open for data exchange rather than immediately reporting success/failure and closing, which looks identical to a hung connection to someone unfamiliar with the flag.

### 5.2 Legacy Port Testing With `telnet`

**Purpose:** Test raw TCP connectivity to a port using a tool present on nearly every system, including older or minimal images where `nc` may not be installed.

**Syntax:**

```bash
telnet <host> <port>
```

**Example usage and expected output:**

```bash
$ telnet mail.example.com 25
Trying 198.51.100.25...
Connected to mail.example.com.
Escape character is '^]'.
220 mail.example.com ESMTP Postfix

# vs. a closed port:
$ telnet mail.example.com 26
Trying 198.51.100.25...
telnet: Unable to connect to remote host: Connection refused
```

**Production usage example:** Because `telnet` completes the TCP handshake and then sits in an interactive session, it's still occasionally used deliberately (not just as a `nc` substitute) to manually type protocol commands against text-based protocols like SMTP — the `220 ... ESMTP Postfix` banner above confirms not just that the port is open but that a real SMTP server answered, one step beyond a bare TCP test.

**Common errors:** Assuming `telnet` is unavailable on modern minimal container images (many Alpine/distroless images genuinely don't ship it) and wasting time debugging "command not found" as if it were a connectivity problem — check for `nc` or `curl` as the more commonly pre-installed alternative in modern minimal images.

### 5.3 Protocol-Aware Diagnostics With `curl -v`

**Purpose:** Diagnose HTTP/HTTPS-specific issues by inspecting each stage of the connection — DNS, TCP, TLS, and the HTTP exchange itself — individually.

**Syntax:**

```bash
curl -v <url>
curl -v --resolve <host>:<port>:<ip> <url>   # bypass DNS, target a specific IP
```

**Example usage and expected output:**

```bash
$ curl -v https://api.example.com/health
*   Trying 203.0.113.10:443...
* Connected to api.example.com (203.0.113.10) port 443 (#0)
* ALPN: offers h2,http/1.1
* TLS handshake, Client hello (1):
* TLS handshake, Server hello (2):
* TLS handshake, Certificate (11):
* SSL certificate verify ok.
* Using HTTP2, server supports multiplexing
* [HTTP/2] [1] OPENED stream for https://api.example.com/health
> GET /health HTTP/2
> Host: api.example.com
>
< HTTP/2 200
< content-type: application/json
<
{"status":"ok"}
```

**Production usage example:** Comparing this full, successful trace against a failing one that stops after "Connected... port 443" but before "SSL certificate verify ok" immediately localizes an incident to TLS/certificate configuration rather than networking — this exact pattern is the standard first check when an expiring or misconfigured certificate is suspected, well before pulling logs from the server itself.

**Common errors:** Reading only the final result (success/failure) and ignoring the staged verbose output, which is where the actual diagnostic value lives — a `curl: (60) SSL certificate problem` error and a `curl: (7) Failed to connect` error both look like generic failures at a glance but indicate completely different root causes (certificate trust vs. no network path at all) visible only in the `-v` detail.

## 6. Production Usage Notes

- `curl --resolve` is a valuable technique for bypassing DNS entirely and pointing a request directly at a specific IP — this isolates whether a failure is DNS-related or genuinely about the target host/service, and is especially useful when testing one node behind a load balancer directly.
- In containerized environments, minimal base images (`distroless`, `scratch`, or slim Alpine variants) frequently ship none of these three tools at all — teams often add a dedicated "debug" sidecar or ephemeral debug container image (with `curl`, `nc`, and `dig`) specifically for troubleshooting, rather than bloating production images with diagnostic tooling.
- `nc`'s behavior and flag set differ meaningfully between the traditional BSD `netcat` and the GNU/`ncat` (from the Nmap project) variants — the `-z` flag in particular is not universal, so confirming which variant is installed (`nc -h`) avoids confusing flag-not-recognized errors during an incident.

## 7. Security Considerations

- Port scanning with `nc` across a range of ports, even against your own infrastructure, can trigger intrusion detection systems ([§87](../Part10/Section-87-Part10-Intrusion-Detection-Prevention-Systems-IDS-IPS-Conceptual-Overview.md)) or automated blocking — coordinate with the security team before running range scans against production, and prefer targeted single-port tests during routine troubleshooting.
- `curl -v` output can include sensitive material if the request or response contains authentication tokens, cookies, or API keys in headers — verbose output should be treated with the same care as logs when shared in tickets or chat channels, and redacted before pasting into shared/public spaces.
- Using `curl -k`/`--insecure` to bypass TLS certificate verification is a common but risky troubleshooting shortcut — it can mask a genuine certificate problem as "working" and should be used only to confirm the specific hypothesis "is this failing purely due to certificate validation," never left in place in scripts, automation, or as a habitual default.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                  | Resolution Path                                                                                              |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `nc -zv` reports "Connection refused"                            | Port reachable but nothing is listening, or the app explicitly rejected it     | Confirm the service is running and bound to the port (`ss -tlnp`); check application startup logs                |
| `nc -zv` hangs and times out                                     | Firewall/security group silently dropping traffic to that port                | Check security group/NACL/firewall rules ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)-[§90](../Part10/Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md)) for the port; capture on the server side to confirm drop      |
| `curl -v` connects and completes TLS, but returns HTTP 502/504   | Reverse proxy/load balancer can't reach the backend, or backend is unhealthy   | Check backend health checks ([§75](../Part9/Section-75-Part9-Health-Checks-and-Failover-Behavior.md)), backend process status, and load balancer/upstream configuration               |
| `curl -v` fails at the TLS stage ("SSL certificate problem")     | Expired, misconfigured, or self-signed certificate not trusted by the client   | Inspect the certificate chain ([§66](../Part8/Section-66-Part8-Certificate-Authorities-Chains-of-Trust-and-Lets-Encrypt-ACME.md)); confirm expiry and correct hostname match                                    |
| `curl` succeeds directly against an IP but fails by hostname     | DNS resolving to the wrong or stale IP                                        | Use `dig`/`curl --resolve` to compare; proceed to the DNS troubleshooting workflow in [§120](Section-120-Part14-DNS-Troubleshooting-Workflows.md)                       |

## 9. Best Practices

- Escalate diagnostic depth in order: `nc -zv` first (fast, cheap, no protocol assumptions), then `curl -v` once a port is confirmed open but behavior is still wrong — don't skip straight to full protocol tracing when a simpler test would answer the question.
- Keep a small, versioned "debug toolbox" container image with `curl`, `nc`, and `dig` pre-installed for use in minimal-image environments, rather than improvising tool installation mid-incident.
- Use `curl --resolve` or a direct-IP `curl` request as a standard technique to separate DNS issues from actual service issues before escalating either team.

## 10. Common Anti-Patterns / Mistakes

- **Habitually adding `curl -k`/`--insecure` to "make TLS errors go away."** This masks the actual certificate problem rather than diagnosing it, and is dangerous if it ever leaks into production automation or health checks.
- **Running `nc` without `-z` and mistaking the resulting interactive hang for a connectivity failure.** Always include `-z` for a pure yes/no reachability check unless deliberately trying to interact with a text protocol.
- **Pasting raw `curl -v` output containing auth headers or tokens into shared tickets or chat without redaction.** Verbose HTTP tracing frequently exposes exactly the kind of secret material that shouldn't be shared broadly.

## 11. Interview Questions

**🎯 Beginner:** _"How would you check if a remote service on port 8443 is reachable from your machine?"_
**Model answer:** I'd run `nc -zv <host> 8443` for a quick, protocol-agnostic check — a "succeeded" message means the TCP port is open and something is listening; "connection refused" means the port is reachable but nothing is listening (or it actively rejected the connection); a hang followed by a timeout means something is silently dropping the traffic, most likely a firewall or security group.
_What the interviewer is probing for:_ Correct, basic tool usage and the ability to distinguish the three possible outcomes.

**🎯 Intermediate:** _"`curl -v` against your API fails, but you're not sure if it's a DNS, network, or TLS problem. How do you narrow it down?"_
**Model answer:** I'd read the staged verbose output rather than just the final error: if it never reaches "Trying <ip>...", the problem is DNS resolution — I'd check that separately. If it reaches "Connected... port 443" but never gets to "SSL certificate verify ok" or completes the TLS handshake, the problem is TLS/certificate-related. If it completes TLS successfully but the HTTP response itself is wrong (a bad status code or no response body), the problem is at the application or reverse-proxy layer, not networking or TLS at all. I'd also try `curl --resolve` to point directly at a known-good IP to rule DNS in or out definitively.
_What the interviewer is probing for:_ Ability to actually decompose curl's staged output rather than treating any curl failure as one undifferentiated problem.

**🎯 Senior:** _"A backend service is intermittently returning 502s from behind a load balancer, but direct `curl` requests to the backend instances individually always succeed. How would you investigate?"_
**Model answer:** Since direct requests to backend instances succeed but requests through the load balancer intermittently 502, the fault is most likely in the load balancer's own view of backend health or in connection handling between the LB and backends — not in the backends themselves. I'd check the load balancer's health check configuration and results ([§75](../Part9/Section-75-Part9-Health-Checks-and-Failover-Behavior.md)) to see if instances are flapping between healthy/unhealthy, check for connection/keep-alive timeout mismatches between the LB and backend (a very common cause of intermittent 502s, where the backend closes idle connections the LB still considers usable), and correlate the timing of 502s against backend restart/deploy events or autoscaling activity. I'd also use `curl -v` with `--resolve` against each backend IP individually, run repeatedly over time, to see if the intermittent failure is reproducible directly against any single backend even without the LB in the loop.
_What the interviewer is probing for:_ Systems-level reasoning about where a "backends are fine but the whole system isn't" symptom actually lives — the LB/backend boundary rather than either endpoint alone.

**🎯 Architect:** _"How would you standardize connectivity/service testing across a large organization with hundreds of microservices and multiple clouds?"_
**Model answer:** I'd establish a small, standard debug toolkit (a container image with `curl`, `nc`, `dig`, and `mtr` pinned to known-good versions) that every team can pull for ad-hoc troubleshooting, removing the "which tools are even installed here" variance across teams and environments. I'd pair that with standardized health-check endpoints across services (a consistent `/health` or `/readyz` convention) so `curl -v` against any service behaves predictably and is comparable across teams. For proactive detection rather than reactive troubleshooting, I'd wire synthetic checks — scripted `nc -zv` and `curl -v`-equivalent probes — into the monitoring pipeline (feeding into the observability practices covered later in Part 15, [§124](../Part15/Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)-[§130](../Part15/Section-130-Part15-Alerting-on-Network-Layer-Signals.md)) so the staged failure information these tools provide manually is captured and alerted on automatically, with the specific failing stage (DNS, TCP, TLS, HTTP) surfaced directly in the alert rather than requiring someone to re-run the diagnostic by hand during an incident.
_What the interviewer is probing for:_ Organizational thinking — turning ad-hoc, per-engineer tool familiarity into standardized, automatable, cross-team practice.

## 12. Common Misconceptions

1. **"`telnet` and `nc -zv` do the same thing, so it doesn't matter which is used."** `nc -zv` is purpose-built for scanning (immediate connect/disconnect, clean success/failure reporting); `telnet` opens an interactive session and requires manually recognizing success from the banner or connection message, making it more error-prone for pure reachability testing.
2. **"A `curl` failure is a single kind of error."** `curl -v`'s value comes precisely from the fact that failures happen at distinguishable stages (DNS, TCP, TLS, HTTP) each with a different meaning and owner — reading only the final error line discards most of the diagnostic information.
3. **"Using `curl -k` to get past a TLS error is a safe troubleshooting step."** It suppresses the very information needed to diagnose a real certificate problem and should never be left in automation or treated as a fix.
4. **"If `nc -zv` succeeds, the service is healthy."** It only confirms a TCP connection can be established — it says nothing about whether the application behind that port is functioning correctly, which is exactly why `curl -v`'s protocol-level checking exists as the next step.

## 13. 🔑 Key Takeaways

- `nc -zv` answers "is this port open" at Layer 4 without any protocol assumptions; `curl -v` answers "does the protocol on that port actually work correctly" with a staged, inspectable trace through DNS, TCP, TLS, and HTTP.
- `telnet` remains useful as a lowest-common-denominator fallback where `nc` isn't installed, but requires manual interpretation rather than clean pass/fail reporting.
- Decomposing a `curl` failure by stage (DNS vs. TCP vs. TLS vs. HTTP) is the single most valuable technique in this section — it converts "curl doesn't work" into a specific, ownable problem.
- Never leave `curl -k`/`--insecure` in place beyond the immediate diagnostic step that confirms a TLS certificate issue exists.

## 14. Related Concepts & What's Next

[§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md) supplies the Layer 3 reachability tests (`ping`, `traceroute`/`tracert`, `mtr`) that precede the port/service testing covered here in the OSI-layer walk from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md). [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) provides the TLS handshake detail that makes sense of `curl -v`'s TLS-stage output, and [§120](Section-120-Part14-DNS-Troubleshooting-Workflows.md) extends the DNS-stage discussion here into a full DNS troubleshooting workflow. [§118](Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md) moves one level deeper still — when port/service testing narrows a problem but doesn't fully explain it, packet capture with `tcpdump` provides the on-the-wire evidence these higher-level tools can't show directly.

**Next Section:** [§118](Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md) — `Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md`
