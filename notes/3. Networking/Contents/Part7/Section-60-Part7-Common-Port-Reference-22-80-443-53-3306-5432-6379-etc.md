# Section 60 (Part 7): Common Port Reference (22, 80, 443, 53, 3306, 5432, 6379, etc.)

## 1. Definition

**Plain language:** A relatively small handful of port numbers show up constantly across nearly every infrastructure engineer's day-to-day work — SSH, web traffic, DNS, and a few common databases and caches chief among them. Knowing these numbers cold, the way you know a phone country code, saves constant lookups and lets you read a firewall rule, a `ss` listing, or a packet capture instantly instead of pausing to guess what a given port is for.

**Precise definition:** This section is a **curated, memorization-oriented reference** of the transport-layer port numbers most frequently encountered in cloud, DevOps, and infrastructure engineering contexts, organized by functional category: remote administration, web traffic, name resolution, and common data-tier services. Each entry states the **protocol (TCP/UDP, or both)**, whether the service is conventionally exposed publicly or kept internal-only, and a short note on production relevance. This is not an exhaustive IANA port registry — it is the practical subset an infrastructure engineer is expected to recognize immediately, without lookup, in production troubleshooting, security review, and infrastructure-as-code work.

> 💡 **Tip:** The fastest way to actually retain this table is to tie each port to a **mental category** rather than memorizing numbers in isolation: "22 and friends" for remote access, "80/443" for web, "53" for naming, and "3306/5432/6379" as "the data tier ports that should almost never be open to the public internet." Categorizing this way also directly informs the security instinct in [§7](../Part1/Section-07-Part1-Prerequisites-Recap-and-How-This-Knowledge-Base-Is-Organized.md) below — most of the entries in the data-tier category are exactly the ports that should never appear in a public-facing security group rule.

## 2. Why This Matters

- **Firewall, security group, and NACL rules are read and written in terms of these exact numbers daily** ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md), [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md), [§90](../Part10/Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md)) — fluency here is a direct productivity and accuracy multiplier for infrastructure work, not just trivia.
- **Security reviews and audits are substantially built around recognizing exposed common ports** — an internet-facing security group with port 3306 or 6379 open to `0.0.0.0/0` is one of the single most common and severe findings in cloud security audits, and recognizing it instantly (rather than looking it up) is expected of any infrastructure engineer.
- **Packet captures and `ss`/`netstat` output are unreadable at speed without this vocabulary** — every troubleshooting workflow in Part 14 assumes the engineer can glance at a port number and immediately know roughly what it represents.
- **Infrastructure-as-code and container manifests reference these ports by number constantly** (security group rules, Kubernetes Service `port`/`targetPort` fields, Dockerfile `EXPOSE` directives) — misremembering a port number in code is a subtle, easy-to-introduce bug.
- **Certification exams and technical interviews test this reference knowledge directly and frequently**, often as quick-fire questions used to establish baseline credibility before moving to deeper topics.

## 3. Prerequisites and Dependencies

This section is a direct, practical continuation of [§59](Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md)'s port-range conventions (well-known, registered, ephemeral) — every port listed here falls into the well-known (0–1023) or registered (1024–49151) bands described there. It assumes the TCP/UDP distinction from [§54](Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md) and [§58](Section-58-Part7-UDP-Structure-Use-Cases-and-Trade-Offs-vs-TCP.md), since correctly knowing *which* transport protocol a given service uses (DNS uses both; MySQL and PostgreSQL are TCP-only) is as important as knowing the number itself. No new mechanics are introduced in this section — it is reference material meant to be memorized and returned to, and is referenced extensively by later sections covering firewalls ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)–[§90](../Part10/Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md)), load balancing ([§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md)–[§81](../Part9/Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md)), and application-layer protocols ([§63](../Part8/Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)–[§71](../Part8/Section-71-Part8-gRPC-and-Modern-RPC-Protocol-Concepts.md)).

## 4. Architecture / Conceptual Diagram

```text
   COMMON PORTS BY FUNCTIONAL CATEGORY

   REMOTE ADMINISTRATION
   ├─ 22    TCP        SSH (secure shell, also used for SFTP/SCP, §67)
   ├─ 3389  TCP        RDP (Windows Remote Desktop)
   └─ 23    TCP        Telnet (legacy, unencrypted — avoid in production)

   WEB TRAFFIC
   ├─ 80    TCP        HTTP (unencrypted)
   ├─ 443   TCP        HTTPS (TLS-encrypted HTTP, §65)
   └─ 8080  TCP        Common alternate/internal HTTP (app servers behind a proxy)

   NAME RESOLUTION
   └─ 53    TCP + UDP  DNS (UDP for most queries, TCP for large responses/zone
                         transfers, §44–§53)

   EMAIL (Part 8, §68)
   ├─ 25    TCP        SMTP (mail relay/transfer)
   ├─ 587   TCP        SMTP submission (authenticated client → server)
   ├─ 143   TCP        IMAP
   └─ 110   TCP        POP3

   FILE TRANSFER (Part 8, §69)
   ├─ 21    TCP        FTP control channel
   └─ 22    TCP        SFTP (rides on SSH, not a separate port)

   RELATIONAL DATABASES
   ├─ 3306  TCP        MySQL / MariaDB
   └─ 5432  TCP        PostgreSQL

   CACHES / IN-MEMORY STORES
   ├─ 6379  TCP        Redis
   └─ 11211 TCP + UDP  Memcached

   SEARCH / DOCUMENT STORES
   ├─ 9200  TCP        Elasticsearch (HTTP API)
   └─ 27017 TCP        MongoDB

   INFRASTRUCTURE / ORCHESTRATION
   ├─ 2379  TCP        etcd client API (Kubernetes control plane)
   ├─ 6443  TCP        Kubernetes API server
   └─ 179   TCP        BGP (routing, §32)

   NETWORK SERVICES
   ├─ 67/68 UDP        DHCP (server/client, §24)
   ├─ 123   UDP        NTP (time sync)
   └─ 161   UDP        SNMP

   ── Data-tier ports (3306, 5432, 6379, 9200, 27017, 2379) should almost
      NEVER appear in a security group rule open to 0.0.0.0/0 — see §7.
```

- Notice **port 22 does double duty** — it's both the SSH remote-shell port and the transport for SFTP/SCP file transfer, since both ride on the SSH protocol itself rather than opening a separate port.
- **Port 53 is the one entry that genuinely spans both TCP and UDP** as a normal, expected part of its operation (not merely "supports both" as a fallback) — UDP for the overwhelming majority of ordinary queries, TCP specifically for oversized responses and zone transfers ([§48](../Part6/Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md)).
- The **infrastructure/orchestration category** (etcd, Kubernetes API server) is a newer but now equally essential addition to this reference for any engineer working with modern container platforms — these ports carry cluster-critical, highly sensitive traffic and deserve exactly the "restrict to trusted sources" treatment as the data-tier ports.

## 5. Hands-On

### 5.1 Cross-Referencing Port Numbers With `/etc/services`

**Purpose:** Show that this reference table isn't arbitrary — it reflects a real, standardized, locally-available mapping most Linux systems ship with.

**Syntax:**

```bash
grep -w <port> /etc/services
```

**Example usage and expected output:**

```bash
$ grep -w 443 /etc/services
https           443/tcp
https           443/udp                # HTTP/3 (QUIC), §62
$ grep -w 3306 /etc/services
mysql           3306/tcp
```

- `/etc/services` is the canonical local reference many command-line tools (like `ss` without `-n`) consult to translate a raw port number into a human-readable name — this is exactly why `ss -tan` (without `-n`) sometimes shows `https` instead of `443`.

**Production usage example:** Engineers unfamiliar with a specific port encountered in a log or capture routinely check `/etc/services` first, before searching online, since it's instant, offline, and covers the overwhelming majority of standard services.

**Common errors:** Trusting `/etc/services` blindly for **non-standard** deployments — many organizations run services on nonstandard ports deliberately (moving SSH off 22, running an internal API on a registered-range port with no IANA entry), and `/etc/services` will show nothing useful or, worse, an unrelated IANA assignment for that number that doesn't reflect the actual service running there.

### 5.2 Scanning a Host for the Common Ports in This Reference

**Purpose:** Efficiently check which of the standard, high-value ports are open on a given host, as a fast triage step.

**Syntax:**

```bash
nmap -p <port-list> <host>
```

**Example usage and expected output:**

```bash
$ nmap -p 22,80,443,3306,5432,6379 10.0.1.20
PORT     STATE    SERVICE
22/tcp   open     ssh
80/tcp   open     http
443/tcp  open     https
3306/tcp filtered mysql
5432/tcp closed   postgresql
6379/tcp closed   redis
```

- `open` means a service is listening and reachable; `closed` means reachable but nothing is listening (an RST was returned, [§55](Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)); `filtered` means no response was received at all — likely a firewall silently dropping the probe.

**Production usage example:** Security teams run exactly this kind of targeted scan against a host's public IP as a first-pass audit step — seeing `3306/tcp open` on a host's *public* interface is an immediate, high-priority finding requiring investigation, since a database port should essentially never be directly reachable from the public internet.

**Common errors:** Running an unscoped, full-range scan (`nmap -p- <host>`) when a fast, targeted scan against this section's known common-port list would answer the immediate question far more quickly — reserve full-range scans for genuinely comprehensive audits, not routine spot checks.

### 5.3 Confirming Which Common Ports a Host Is Actually Listening On Locally

**Purpose:** Compare externally-observed scan results against the host's own local listening-socket state, to distinguish "not listening" from "listening but firewalled."

**Syntax:**

```bash
ss -tulnp | grep -E ':(22|80|443|3306|5432|6379)\b'
```

**Example usage and expected output:**

```bash
$ ss -tulnp | grep -E ':(22|80|443|3306|5432|6379)\b'
tcp   LISTEN  0  128   0.0.0.0:22       0.0.0.0:*   users:(("sshd",pid=712))
tcp   LISTEN  0  511   0.0.0.0:443      0.0.0.0:*   users:(("nginx",pid=1104))
tcp   LISTEN  0  70    127.0.0.1:3306   0.0.0.0:*   users:(("mysqld",pid=980))
```

- Note MySQL here is bound to `127.0.0.1` (localhost only), not `0.0.0.0` — this is exactly the correct, hardened configuration for a data-tier service: reachable from the local host only, invisible to any external scan regardless of firewall rules, since the service itself never listens on an externally-reachable interface at all.

**Production usage example:** This local-vs-external comparison is standard practice when validating a hardening change — confirming a database was moved to bind on `127.0.0.1` (or a private-only interface) rather than relying solely on a firewall rule to keep it inaccessible, since a bind-address restriction is a strictly stronger control than a firewall rule alone (defense in depth).

**Common errors:** Relying exclusively on firewall rules to protect a data-tier port while leaving the service bound to `0.0.0.0` — a single misconfigured or accidentally-loosened firewall rule then fully exposes the service, whereas a `127.0.0.1`/private-interface bind would have made the same misconfiguration harmless.

## 6. Production Usage Notes

- **Cloud provider managed database and cache services** (RDS, Cloud SQL, Azure Database, ElastiCache, MemoryStore) still use these exact same conventional ports (3306, 5432, 6379) under the hood — the "managed" aspect changes patching and operations, not the fundamental port conventions engineers need to know when writing security group rules for them.
- **Moving SSH off port 22** ("security through obscurity" for reducing automated scan/brute-force noise) is a real, common practice, but it does not change SSH's protocol behavior in any way — it only changes which port number carries it, and should never be relied upon as a primary security control on its own.
- **Container images commonly `EXPOSE` a nonstandard internal port** (Node.js apps on 3000, Spring Boot on 8080) with the platform's ingress/load-balancing layer mapping it to the conventional external port (80/443) — recognizing this pattern prevents confusion when a container's internal port doesn't match the "standard" number for its apparent function.

## 7. Security Considerations

- **The single most common and severe cloud security misconfiguration finding is a data-tier port (3306, 5432, 6379, 9200, 27017) exposed to `0.0.0.0/0`** in a security group or firewall rule — these services were never designed to be safely internet-facing, and exposure of this kind has led to numerous real-world mass-scanning and ransomware incidents against unauthenticated or weakly-authenticated databases and caches found this way.
- **Legacy unencrypted protocols in this reference (Telnet/23, FTP/21, unencrypted HTTP/80, plain SMTP/25 without STARTTLS) should be treated as inherently higher-risk** whenever they appear in a scan or configuration review — the presence of any of these on a production host is itself often a finding worth flagging, independent of whether the specific service is otherwise correctly configured.
- **Kubernetes/etcd control-plane ports (6443, 2379) require the same "never expose to the public internet" discipline as data-tier database ports** — an exposed, unauthenticated etcd endpoint gives an attacker direct access to the entire cluster's configuration and secrets, making it one of the most severe possible findings in a containerized environment.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Likely Cause                                                                 | Resolution Path                                                                                                    |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Application can't connect to its database despite correct credentials  | Security group/firewall not permitting the app's source to reach port 3306/5432 | Verify security group rules allow the application tier's source (not `0.0.0.0/0`) to reach the database's specific port |
| A port scan shows a data-tier port `open` on a host's public interface | Service is bound to `0.0.0.0` and/or a firewall rule is too permissive           | Rebind the service to a private-only interface ([§6](../Part1/Section-06-Part1-Bandwidth-Throughput-Latency-and-Jitter-Core-Vocabulary.md)) and tighten the firewall/security group rule immediately        |
| `ss -tulnp` shows nothing on an expected port                          | The service isn't running, crashed, or is bound to an unexpected interface/port | Check the service's own logs and configuration for its actual configured listen address/port                       |
| Health check against port 8080 fails but the app "works" externally    | The external port (443, via a load balancer) differs from the app's actual internal listen port (8080) — health check misconfigured | Point the health check at the correct internal port and path, matching the actual backend listener                 |

## 9. Best Practices

- Memorize this table's categories, not just isolated numbers — recognizing "this is a data-tier port" instantly is more valuable day to day than recalling the exact number for an obscure, rarely-seen service.
- Treat any data-tier or control-plane port (database, cache, search, etcd, Kubernetes API) found open to a broad or public source range in a security review as a high-priority finding requiring immediate remediation, not a routine cleanup item.
- Prefer binding sensitive services to a private-only interface (`127.0.0.1` or an internal-only IP) in addition to firewall rules — defense in depth means a single misconfigured rule doesn't fully expose the service.

## 10. Common Anti-Patterns / Mistakes

- **Opening a data-tier port to `0.0.0.0/0` "temporarily" for debugging and forgetting to close it.** This single pattern accounts for a disproportionate share of real-world data breaches involving unauthenticated or weakly-secured databases discovered by internet-wide scanners within minutes to hours of exposure.
- **Relying on an unusual port number as a security measure.** Moving a service off its standard port reduces automated scan noise but provides no real protection against a targeted attacker running a full port scan — it is obscurity, not security, and should never substitute for proper authentication and network restriction.
- **Assuming a port number always identifies a specific technology with certainty.** Registered-range ports especially can be reused by different organizations for entirely different, non-standard internal services — always verify what's actually listening rather than assuming purely from the number.

## 11. Interview Questions

**🎯 Beginner:** _"Name the port numbers for SSH, HTTP, HTTPS, and DNS."_
**Model answer:** SSH is port 22 (TCP), HTTP is port 80 (TCP), HTTPS is port 443 (TCP), and DNS is port 53 (using both UDP for most queries and TCP for larger responses and zone transfers).
_What the interviewer is probing for:_ Baseline fluency with the ports every infrastructure engineer is expected to know without hesitation.

**🎯 Intermediate:** _"You find port 6379 open to the public internet on a production host during a security review. What is it, and why is this a serious finding?"_
**Model answer:** Port 6379 is Redis's default port. This is a serious finding because Redis historically has no authentication enabled by default and is designed to be used within a trusted private network, not exposed directly to the internet — an exposed, unauthenticated Redis instance gives any internet-connected attacker full read/write access to whatever data it holds, and has historically been a common vector for ransomware and cryptomining compromise campaigns that specifically scan for exactly this misconfiguration.
_What the interviewer is probing for:_ Whether the candidate recognizes this as a severe, well-known, actively-exploited misconfiguration pattern rather than treating it as a minor finding.

**🎯 Senior:** _"Why does DNS use both UDP and TCP on the same port number, 53, while most other services pick one protocol exclusively?"_
**Model answer:** DNS's primary design goal for ordinary queries is low latency and low overhead — UDP's lack of handshake makes typical small queries and responses faster than a TCP connection would be. But DNS responses can occasionally exceed what fits comfortably in a single UDP datagram (large record sets, DNSSEC-signed responses), and certain operations like zone transfers between DNS servers require reliable, ordered, and potentially large data transfer — needs that map naturally onto TCP. Rather than picking one protocol and compromising one of those two goals, DNS specifies both on the same port number, with resolvers falling back to TCP automatically (often signaled via the truncation bit in a UDP response) when UDP genuinely isn't sufficient.
_What the interviewer is probing for:_ Understanding that this dual-protocol design is a deliberate, purpose-driven engineering choice, not an inconsistency or historical accident.

**🎯 Architect:** _"You're designing security group and network policy standards for a multi-team cloud platform used by dozens of engineering teams. How do you operationalize the 'data-tier ports should never be public' principle at scale, beyond just documenting it?"_
**Model answer:** Documentation alone doesn't prevent the mistake at scale — I'd implement it as an automated, enforced guardrail rather than a guideline: policy-as-code checks (in the CI/CD pipeline and/or continuously via a cloud security posture management tool) that specifically flag or outright block any security group rule opening known data-tier ports (3306, 5432, 6379, 9200, 27017, 2379, 6443, and similar) to `0.0.0.0/0` or overly broad CIDR ranges, regardless of which team or account created the rule. I'd pair this with default-deny security group templates provided centrally (so teams start from a safe baseline rather than an open one) and periodic automated scanning of the actual deployed environment (not just the declared infrastructure-as-code) to catch drift or manually-introduced exceptions. Finally, I'd make the exception process explicit and reviewed — if a team has a genuine, rare reason to expose such a port more broadly, that should require documented justification and security sign-off rather than being silently possible by default.
_What the interviewer is probing for:_ Ability to think beyond "know the rule" to designing organizational, automated systems that make the mistake structurally difficult to make at scale — a hallmark of senior/architect-level security thinking.

## 12. Common Misconceptions

1. **"A port number uniquely and permanently identifies a specific technology."** Especially in the registered range, port numbers are conventions, not guarantees — always verify what's actually running rather than assuming purely from the number, particularly for internal or nonstandard services.
2. **"Moving a service off its default port is a meaningful security control."** It reduces automated scanning noise but provides no protection against a targeted, thorough scan — it must never substitute for actual authentication and network access restriction.
3. **"If a firewall rule blocks a port, the underlying service is safe even if misconfigured to listen on a public interface."** Defense in depth matters specifically because firewall rules can be accidentally loosened or misconfigured — binding sensitive services to private-only interfaces is a stronger, independent layer of protection.
4. **"DNS is a UDP-only protocol."** It's dual-protocol by design, using TCP for oversized responses and zone transfers — treating it as UDP-only leads to firewall rules that inadvertently block legitimate DNS operations requiring TCP.

## 13. 🔑 Key Takeaways

- A small, well-defined set of ports (22, 80, 443, 53, 3306, 5432, 6379, and a handful of others) accounts for the overwhelming majority of ports encountered in real infrastructure work, and should be recognized on sight.
- Data-tier and control-plane ports (databases, caches, search engines, etcd, Kubernetes API servers) should essentially never be exposed to the public internet — this is among the most common and most severe real-world cloud security misconfigurations.
- `/etc/services` provides a useful local reference for standard port-to-service mappings but does not reflect nonstandard or custom deployments.
- Binding sensitive services to a private-only interface is a stronger, independent security control than a firewall rule alone, and the two should be used together.
- Port number conventions inform, but never substitute for, actually verifying what is listening on a given port during troubleshooting or security review.

## 14. Related Concepts & What's Next

[§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md) shifts from the static port reference built here to the dynamic behavior of TCP connections over time, walking through the complete state machine — including exactly how a listening socket on one of these well-known ports transitions through connection states as clients connect and disconnect. [§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md) and [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) (Part 10) apply this port reference directly to writing and auditing firewall and security group rules. [§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md) (Part 8) covers TLS in depth, the protocol that turns port 80's traffic into port 443's, and [§67](../Part8/Section-67-Part8-SSH-Protocol-Structure-Key-Exchange-and-Tunneling.md) covers SSH's protocol internals beyond the port number introduced here.

**Next Section:** [§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md) — `Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md`
