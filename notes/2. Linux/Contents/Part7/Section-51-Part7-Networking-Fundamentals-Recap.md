# Section 51 (Part 7): Networking Fundamentals Recap (IP, TCP/UDP, DNS, Routing)

## 1. Why This Is a Recap, Not a Networking Course

§50 closed out Part 6's shell/scripting/text-processing toolkit by noting that regex resurfaces almost immediately in Part 7 — parsing `ss`, `dig`, and log output leans on the exact same pattern-matching habits, just pointed at network-facing text. This section is where that pivot happens.

This is deliberately a **fast refresher**, not a from-scratch networking course. The assumption (00-Roadmap.md, §2) is that basic IP/DNS concepts are already familiar in outline; what this section does is ground those concepts specifically in **how Linux exposes and represents them** — the commands, files, and terminology a Linux administrator actually touches — so Part 7's remaining sections (network config tools in §52, DNS resolution mechanics in §53, firewalls in §54, diagnostics in §55, SSH in §56, file transfer in §57, network services in §58) have a shared, Linux-grounded vocabulary to build on without re-deriving it each time.

> 💡 **Tip:** Treat this section as a checklist of "do I actually know how this looks on a Linux box" rather than "do I know what TCP is." If a concept here feels unfamiliar in the abstract, that's outside this section's scope to fix — if it feels unfamiliar specifically as `ip addr` or `ip route` output, that's exactly what this section addresses.

## 2. IP Addressing: IPv4 Basics as Linux Shows Them

An **IPv4 address** is a 32-bit number conventionally written as four decimal octets separated by dots — **dotted-decimal notation** — e.g. `192.168.1.10`, each octet ranging 0–255.

**CIDR notation** (`/24`, `/16`, etc.) expresses how many leading bits of the address are the **network portion** versus the **host portion**, replacing the older, less flexible class-based (Class A/B/C) scheme almost entirely in modern practice. `192.168.1.10/24` means the first 24 bits (`192.168.1`) identify the network and the remaining 8 bits identify the specific host within it — up to 254 usable host addresses (256 minus the network and broadcast addresses).

**Private vs. public ranges** matter operationally because private ranges are never globally routable — they only have meaning inside a given network and require NAT (network address translation, typically at a router/gateway/cloud load balancer) to reach or be reached from the public internet:

| Range                           | CIDR             | Common use                                                     |
| ------------------------------- | ---------------- | -------------------------------------------------------------- |
| `10.0.0.0`–`10.255.255.255`     | `10.0.0.0/8`     | Large private networks (common in cloud VPCs)                  |
| `172.16.0.0`–`172.31.255.255`   | `172.16.0.0/12`  | Private networks (Docker's default bridge range overlaps here) |
| `192.168.0.0`–`192.168.255.255` | `192.168.0.0/16` | Small/home/office private networks                             |
| `127.0.0.0`–`127.255.255.255`   | `127.0.0.0/8`    | Loopback (localhost) — never leaves the host                   |

Everything outside these reserved ranges (plus a handful of other special-purpose blocks) is potentially a **public**, globally routable address.

On a Linux host, the tool for viewing this directly is `ip addr` (or `ip addr show`, `ip a` as the common shorthand):

```bash
$ ip addr show eth0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff
    inet 172.17.0.2/16 brd 172.17.255.255 scope global eth0
       valid_lft forever preferred_lft forever
```

The `inet 172.17.0.2/16` line is the address-plus-CIDR pairing directly — this interface's IP and its network's prefix length in one string, exactly the notation from above. Full `ip` command coverage (assigning addresses, bringing interfaces up/down, and the broader `ip`/`nmcli`/`netplan` toolchain) is §52's job, not this section's — here the point is just recognizing what the output means.

> ⚠️ **Warning:** `ifconfig` still shows up in older tutorials, forum answers, and inherited scripts, but it's deprecated on modern distributions (part of the unmaintained `net-tools` package) in favor of `ip` (part of `iproute2`). Seeing `ifconfig` in a script or runbook is itself a signal the material may be stale — §55 and Part 15 (§114) return to this deprecated-tools pattern in more depth.

## 3. TCP vs. UDP: The Conceptual Difference That Drives Real Config Choices

TCP and UDP are both **transport-layer protocols** riding on top of IP, and the difference between them isn't academic trivia — it's a decision every service configuration on a Linux host implicitly makes.

**TCP (Transmission Control Protocol)** is **connection-oriented and reliable**: it establishes a handshake before data flows, guarantees delivery and ordering (retransmitting lost packets, reordering out-of-order ones), and tears the connection down explicitly when done. This reliability has a cost — more overhead, more round trips, and state that must be tracked for the life of the connection.

**UDP (User Datagram Protocol)** is **connectionless and unreliable**: packets (datagrams) are fired off with no handshake, no delivery guarantee, and no ordering guarantee. A datagram can be lost, duplicated, or arrive out of order, and UDP itself does nothing about it. What it trades away in reliability it gains back in low overhead and low latency.

**Why this is a real Linux service-config decision, not trivia:** when a daemon binds a port, TCP vs. UDP is an explicit choice baked into that service's design and its config file, not an implementation detail an administrator can ignore:

- **SSH, HTTP/HTTPS, most databases** — TCP, because a dropped or reordered byte in an SSH session or a database query is not acceptable; the application needs the reliability guarantee.
- **DNS queries, NTP/chrony time sync, most VoIP/streaming, SNMP** — UDP, because retransmission overhead would hurt more than an occasional lost packet does, and many of these protocols implement their own lightweight retry logic on top rather than paying TCP's cost. (DNS is a partial exception — see 6 and §53 — it uses UDP for ordinary queries but falls back to TCP for large responses like zone transfers.)
- **A firewall rule, a `systemd` socket unit, or an `nftables`/`iptables` rule (§54) must specify protocol explicitly** — opening TCP/53 does not open UDP/53, and a service configured to listen on UDP will simply never receive traffic sent to it over TCP. This is a routine, concrete source of "the port is open but the service still doesn't work" incidents.

> 💡 **Tip:** When troubleshooting "I opened the port but it still doesn't connect," checking whether the firewall rule and the service's actual listening protocol (TCP vs. UDP) match is one of the first, cheapest things to verify — `ss` (full coverage in §55) shows exactly which protocol a service is actually bound to.

## 4. Ports: Well-Known Range vs. Ephemeral Range

A **port** is a 16-bit number (0–65535) that, combined with an IP address and a protocol (TCP or UDP), uniquely identifies one endpoint of a network connection — the mechanism that lets a single host run many independent network services simultaneously without them colliding.

Two ranges matter operationally:

- **Well-known ports (0–1023)** — reserved for standard, widely recognized services: 22 (SSH), 53 (DNS), 80 (HTTP), 443 (HTTPS), 3306 (MySQL), 5432 (PostgreSQL), and so on. On Linux, binding to a port in this range historically required root privileges (or, on modern kernels, the `CAP_NET_BIND_SERVICE` capability specifically) — a security-relevant detail worth remembering when a service unexpectedly fails to start with a permissions error on a low port number.
- **Registered ports (1024–49151)** — assigned to specific applications by convention (e.g. 8080 for alternate HTTP, 6379 for Redis) but not requiring elevated privilege to bind.
- **Ephemeral (dynamic/private) ports (49152–65535, though the exact usable range is kernel-configurable)** — the range the kernel allocates _from_ automatically for the client side of an outbound connection. When a Linux host makes an outbound HTTP request, the kernel picks an unused port from this range as the local (source) port for that connection; the administrator never assigns it directly.

```bash
$ cat /proc/sys/net/ipv4/ip_local_port_range
32768   60999
```

This file shows the actual ephemeral range in use on a given host — it's tunable via `sysctl` and occasionally matters at scale (a host making a very high volume of outbound connections can exhaust its ephemeral port range faster than the default suggests, a real capacity constraint worth knowing exists even though full `sysctl` tuning is out of scope here).

> ⚠️ **Warning:** Don't confuse "the well-known range" with "the only ports services use" — plenty of legitimate, common services (Redis on 6379, Prometheus on 9090, countless custom application ports) live well above 1023. The well-known range is a convention with real privilege implications below 1024, not an exhaustive list of ports worth knowing.

## 5. Network Interfaces: How Linux Names and Represents Them

A **network interface** is the kernel's abstraction for a network-connected device — physical (an Ethernet NIC, a Wi-Fi adapter) or virtual (a loopback interface, a bridge, a VPN tunnel, a container's virtual Ethernet pair).

**Loopback (`lo`)** exists on every Linux host regardless of physical networking hardware — it's a fully virtual interface bound to `127.0.0.1` (and `::1` for IPv6) that lets a host talk to itself over the network stack without traffic ever leaving the machine. Services binding to `127.0.0.1` specifically (as opposed to `0.0.0.0`) are deliberately restricting themselves to local-only access — a distinction that resurfaces constantly in security hardening (Part 12) and container networking (Part 13).

**Interface naming has gone through a real, disruptive convention change** worth recognizing on sight:

- **Legacy naming** — `eth0`, `eth1`, `wlan0` — simple, sequential, but not guaranteed stable: on a host with multiple NICs, which physical card became `eth0` versus `eth1` could shift across reboots or kernel/driver updates, based on device enumeration order rather than anything physically fixed.
- **Predictable naming** (`systemd`-based, the modern default on most distributions) — names like `ens192`, `enp0s3`, `eno1` — encode information about the device's actual physical/virtual location (bus, slot, on-board position) directly into the name, so the same physical NIC gets the same interface name across reboots regardless of enumeration order.

```bash
$ ip addr show
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    inet 127.0.0.1/8 scope host lo
2: ens192: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    inet 10.0.1.15/24 brd 10.0.1.255 scope global ens192
```

> 💡 **Tip:** Seeing `eth0` on a modern distribution isn't necessarily wrong — cloud provider images and container base images frequently keep legacy-style naming deliberately, since predictable naming's whole value proposition (stability across multiple physical NICs) is largely moot on a single-NIC cloud instance or container. Don't treat `eth0` alone as evidence of an old or misconfigured host; treat it as a naming-scheme choice.

## 6. Routing and the Default Gateway, as Linux Exposes Them

Every Linux host maintains a **routing table** — the kernel's lookup structure for deciding, given a destination IP address, which interface and which next-hop address a packet should actually be sent through. `ip route` (or `ip route show`, `ip r`) shows it directly:

```bash
$ ip route show
default via 10.0.1.1 dev ens192
10.0.1.0/24 dev ens192 proto kernel scope link src 10.0.1.15
```

Reading this:

- The `default via 10.0.1.1 dev ens192` line is the **default route** — where a packet goes when no more specific route matches its destination. `10.0.1.1` here is the **default gateway**, typically the local router/firewall responsible for forwarding traffic on toward its actual destination beyond the local network.
- The `10.0.1.0/24 dev ens192 ... scope link` line is a **directly connected route** — traffic to any address in `10.0.1.0/24` doesn't need the gateway at all, because it's on the same local network segment reachable straight out of `ens192`.

The kernel evaluates routes by **specificity** (longest prefix match) — a more specific route (a smaller, more precisely scoped CIDR block) always wins over a broader one, with the default route (effectively `0.0.0.0/0`, matching everything) acting as the catch-all fallback when nothing more specific applies.

> ⚠️ **Warning:** A missing or wrong default gateway is one of the most common "this host can reach other machines on its own subnet but can't reach anything else" symptoms — local-subnet traffic uses the directly-connected route and works fine, while everything else silently has nowhere to go. `ip route show` is the first thing worth checking, not last, when a host has partial-but-not-total connectivity. Full diagnostic workflow (`ping`, `traceroute`, `ss`, `tcpdump`) is §55's territory — this section is only about recognizing what the routing table itself means.

## 7. DNS: Conceptual Only — Full Mechanics Deferred to §53

**DNS (Domain Name System)** exists to solve one problem: humans and applications want to refer to hosts by name (`example.com`), but IP routing (6) only understands addresses. DNS is the distributed, hierarchical lookup system that resolves a name to an address (and back, and to other record types — mail servers, text records, and more) on request.

At the conceptual level worth holding here: a DNS **query** asks a **resolver** (often a local or ISP-provided one, sometimes a public one like `8.8.8.8` or `1.1.1.1`) to resolve a name; the resolver either answers from cache or walks the DNS hierarchy (root servers → TLD servers → authoritative servers for the specific domain) to find the authoritative answer, then returns it. Ordinary lookups use UDP (3) for their low overhead, with TCP as a fallback for responses too large for a single UDP datagram.

That's genuinely as deep as this section goes. **How a Linux host specifically decides which resolver to ask, in what order, and how results get cached or overridden locally** — `/etc/resolv.conf`, `/etc/hosts`, `nsswitch.conf`, and the tools for querying DNS directly (`dig`, `nslookup`) — is **§53's full, dedicated treatment**, immediately next in this Part. Anything more here would just be duplicated there with less depth.

## 8. Common Misconceptions

1. **"CIDR notation is just a fancier way of writing a subnet mask."** They express the same underlying information (how many bits are network vs. host) but CIDR's `/N` form is the notation actually used in nearly all modern Linux tooling output (2) — fluency in reading `/24`-style notation directly, without mentally converting to a dotted subnet mask first, is the practical skill worth having.
2. **"TCP is just 'better' than UDP and UDP is a legacy fallback."** They're suited to different problems, not ranked — UDP's lack of overhead is a deliberate, correct choice for DNS queries, time sync, and streaming, not a compromise (3). A service using UDP is not "using the worse protocol"; it's making a latency/reliability tradeoff that fits its use case.
3. **"A port being 'open' in a firewall rule means the service is reachable."** A firewall rule and a service's actual listening protocol/state are two separate things that both have to be correct — opening TCP/8080 in a firewall does nothing for a service listening on UDP/8080, and neither helps if the service isn't actually running or bound at all (3, 4). `ss` (§55) is what confirms the service side; the firewall (§54) is only half the picture.
4. **"`eth0` means an old or misconfigured system."** Predictable naming (`ens192`, `enp0s3`) is the modern default on many distributions, but plenty of current, correctly configured cloud instances and containers deliberately keep legacy-style names because the stability problem predictable naming solves barely applies to a single-NIC host (5).
5. **"The default route only matters for internet-bound traffic."** It matters for **any** destination not covered by a more specific route in the table — which in practice is usually "everything off the local subnet," internet or not; a host with no route to a different internal subnet fails via the exact same missing-default-gateway mechanism as a host with no route to the public internet (6).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What does the `/24` in `192.168.1.0/24` actually mean?"_
**Model answer:** It's CIDR notation indicating that the first 24 bits of the 32-bit IPv4 address are the network portion, leaving the remaining 8 bits for host addresses within that network — giving up to 254 usable host addresses (256 minus the network and broadcast addresses). It's the modern replacement for the older class-based addressing scheme and is what `ip addr` and routing tables actually display on Linux.
_What the interviewer is probing for:_ Basic fluency reading the notation that appears in essentially every piece of Linux networking output, not memorized subnetting arithmetic.

**🎯 Intermediate:** _"A service is configured to listen on UDP/514 for syslog, but a monitoring tool keeps reporting the port as unreachable even though a firewall rule for TCP/514 exists. What's going on?"_
**Model answer:** TCP and UDP are separate protocols with separate port spaces as far as firewall rules and service binding are concerned — a firewall rule opening TCP/514 does nothing for traffic arriving over UDP/514, and vice versa. Since the service is actually listening on UDP, the fix is adding a UDP/514 rule (or fixing whichever side — firewall rule or service config — was configured against the wrong protocol), not further troubleshooting the TCP rule that was never relevant. Confirming the service's actual listening protocol with `ss` before touching firewall rules would have caught this immediately.
_What the interviewer is probing for:_ Recognizing that protocol mismatch between firewall config and actual service binding is a real, common failure mode, not a hypothetical edge case.

**🎯 Senior:** _"A host can reach every machine on its own /24 subnet but nothing outside it, and DNS lookups are timing out too. Walk through your diagnosis using only routing and interface concepts, without running any tool yet."_
**Model answer:** Working traffic within the local subnet but nothing beyond it is the classic signature of the directly-connected route working while the default route either is missing, points to a dead/wrong gateway, or the gateway itself has lost its own upstream path. The DNS timeout is consistent with, not contradictory to, that diagnosis — if the configured DNS resolver's IP is off-subnet (very common, since resolvers are frequently a public IP like a provider's recursive resolver or an internal DNS server on a different subnet), DNS queries would fail for exactly the same reason as any other off-subnet traffic: no working default route to reach them. I'd check `ip route show` first for a missing or misdirected default route before assuming this is a DNS-specific problem at all — it's very plausible the "DNS issue" is actually a routing issue wearing a DNS-shaped symptom.
_What the interviewer is probing for:_ Ability to reason about layered failure symptoms — recognizing that a DNS symptom can have a routing root cause — rather than treating each protocol layer in isolation.

**🎯 Architect:** _"You're designing the network segmentation for a new service tier. What from this section's fundamentals directly shapes real architectural decisions, versus what's just background knowledge?"_
**Model answer:** Private-vs-public addressing (2) directly drives whether a tier needs NAT/a load balancer at all to be reachable, and CIDR sizing decisions (how large a subnet each tier gets) have real operational cost if undersized later — resizing a live subnet is disruptive, so I'd size for realistic multi-year host-count growth up front. TCP-vs-UDP (3) isn't just a config detail per service — it directly shapes what the firewall/security-group rule set has to look like, and mismatches between the two are a recurring, avoidable source of "why can't this reach that" incidents, so I'd want firewall rules generated from the same source of truth as service definitions rather than maintained separately by hand. The well-known-vs-ephemeral port distinction (4) matters concretely for outbound-heavy services at scale — a host or NAT gateway making very high connection volume can exhaust its ephemeral port range, which is a real capacity constraint to plan for, not trivia. And the default-route/gateway model (6) is exactly what determines whether a segmentation design actually achieves its isolation goal — a subnet with a route back to something it's supposed to be isolated from defeats the purpose of the segmentation regardless of what the firewall rules say on paper.
_What the interviewer is probing for:_ Connecting textbook-level fundamentals to concrete architectural and capacity-planning consequences, not just reciting definitions.

## 10. Key Takeaways

- CIDR notation (`/24`, etc.) is the practical, modern way network prefixes are expressed and is what `ip addr`/`ip route` actually show — fluency reading it directly matters more than manual subnet-mask arithmetic (2).
- Private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) and loopback (`127.0.0.0/8`) are never globally routable on their own; `ip addr` is the Linux-native way to see what's actually assigned to an interface (2, 5).
- TCP (connection-oriented, reliable) vs. UDP (connectionless, unreliable but low-overhead) is a real per-service configuration choice on Linux, not an implementation footnote — firewall rules and service bindings must match protocol, and mismatches are a common, concrete troubleshooting scenario (3).
- Ports below 1024 are the well-known range (historically privilege-gated to bind), 1024–49151 are registered, and the top range is ephemeral — allocated automatically by the kernel for outbound connections and occasionally a real capacity constraint at scale (4).
- Linux interface naming has shifted from legacy sequential names (`eth0`) to predictable, location-encoded names (`ens192`, `enp0s3`) — neither is inherently "correct"; `eth0` on a modern single-NIC cloud instance or container is a normal, deliberate choice, not a red flag (5).
- The routing table (`ip route show`) and default gateway determine where traffic goes when no more specific route matches — a missing/wrong default route produces the classic "local subnet works, nothing else does" symptom, and can masquerade as a DNS problem when the resolver itself is off-subnet (6).
- DNS is covered here at concept level only (query → resolver → hierarchy, UDP with TCP fallback) — full Linux-specific resolution mechanics (`/etc/resolv.conf`, `/etc/hosts`, `nsswitch.conf`, `dig`) are §53's dedicated depth, deliberately not duplicated here (7).

## 11. Related Concepts & What's Next

This section is Part 7's opening recap, picking up directly from §50's note that regex resurfaces immediately when parsing network-facing tool output. It assumes the general IP/TCP/UDP/DNS concepts as prior background (00-Roadmap.md §2) and focuses specifically on how Linux represents them via `ip addr` and `ip route`. §52 (next) covers the actual configuration tools — `ip`, `nmcli`, `netplan`, and legacy `/etc/network/interfaces` — for changing what this section showed how to read. §53 delivers the full DNS-resolution depth this section deliberately deferred. §55, later in this Part, builds the full diagnostic toolkit (`ping`, `traceroute`, `ss`, `netstat`, `tcpdump`, `dig`, `curl`) for troubleshooting everything introduced here.

**Next Section:** §52 — `Section-52-Part7-Network-Configuration-Tools.md`
