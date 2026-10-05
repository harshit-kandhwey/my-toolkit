# Section 47 (Part 6): Network Troubleshooting Tools and Techniques

## 1. Definition

**Plain language:** Container networking problems are solved by asking, layer by layer, "where does the packet stop?" The skill is knowing which tool answers each question and how to run it *from inside the container's network namespace* when the image itself has no tools.

**Precise definition:** A repeatable method (identify scope, then test DNS, routing, connectivity, firewall/NAT, and application layers in order) combined with a toolbox: `docker network inspect`, `docker inspect`, `docker exec`, a debug sidecar (for example `nicolaka/netshoot`) that shares the target's network namespace via `--network container:<name>`, host-side `nsenter`, `ip`, `ss`, `tcpdump`, `iptables`/`nft`, `conntrack`, `dig`, `curl` and `ping`/`traceroute`.

> 💡 **Tip:** Production images are often distroless or minimal and contain no `ip`, `curl` or `ping`. Do not install tools into them; attach a debug container to the same namespace instead.

## 2. Why This Matters

- Network faults look identical from the application ("connection refused", "timeout", "name not resolved") but have completely different causes at different layers.
- Without a method, engineers restart containers at random and destroy the evidence.
- Minimal images force you to know the namespace-sharing techniques, which are also the safest way to debug in production.
- Troubleshooting scenarios are the most common practical interview and incident-response task ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md), [§102](../Part14/Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md)).

## 3. Prerequisites and Dependencies

Assumes the Part 6 model: drivers ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), bridges and veth pairs ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), embedded DNS at `127.0.0.11` ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), NAT and published ports ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)) and overlays ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)). Namespaces underpin the whole approach ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)); `exec` mechanics are in [§28](../Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md) and `docker run` flags in [§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md). Linux host access is needed for `nsenter` and `tcpdump` on the host; on Docker Desktop the host tools run inside the Linux VM.

## 4. Architecture / Conceptual Diagram

```text
  Symptom: "service A cannot reach service B"

  1 ► Is B actually running and listening?     docker ps / logs / ss -ltn (in B)
  │      listening on 0.0.0.0, not 127.0.0.1?
  ▼
  2 ► Are A and B on a common network?         docker network inspect / docker inspect
  │
  ▼
  3 ► Does the NAME resolve (in A)?            getent hosts B / dig B  (resolver 127.0.0.11)
  │
  ▼
  4 ► Does the IP route and answer?            ip route / ping / traceroute / nc -zv B 8080
  │
  ▼
  5 ► Is something dropping or rewriting?      iptables -S / nft list ruleset / tcpdump / conntrack
  │
  ▼
  6 ► Does the application protocol work?      curl -v / openssl s_client / app logs

  Where each tool looks
  ┌───────────────────────────────────────────────────────────────────────┐
  │ Host namespace   iptables, nft, conntrack, tcpdump -i docker0/br-xxxx │
  │        ▲                                                              │
  │        │  nsenter -t <pid> -n          docker run --network container:A │
  │        ▼                                                              │
  │ Container netns  ip a, ip r, ss, dig, tcpdump -i eth0                 │
  └───────────────────────────────────────────────────────────────────────┘
```

- **Work bottom-up from the symptom's error text:** "name or service not known" is step 3; "connection refused" means the IP was reached but nothing listens (steps 1 or 6); "timed out" means packets vanished (steps 2, 4 or 5).
- **Two vantage points:** inside the container namespace (what the app sees) and the host namespace (bridges, NAT, firewall).
- **Debug sidecar principle:** a new container started with `--network container:<target>` shares the same interfaces, routes, DNS and listening sockets, but has its own filesystem full of tools.

## 5. Hands-On

### 5.1 Inspect Wiring: Networks, IPs, Aliases

```bash
docker network ls
docker network inspect appnet --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'
docker inspect api --format '{{json .NetworkSettings.Networks}}' | jq 'keys, (.[] | {IPAddress, Aliases, Gateway})'
docker port web
```

```text
bridge
host
none
appnet
web 172.20.0.2/16
api 172.20.0.3/16
80/tcp -> 0.0.0.0:8080
```

If `api` and `web` do not share a network name in `NetworkSettings.Networks`, stop here: they cannot resolve each other by name on a user-defined network ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)).

### 5.2 Use a Debug Sidecar in the Target's Namespace

```bash
docker run --rm -it --network container:api nicolaka/netshoot
```

```text
 api-debug  ~  ip -br a
lo      UNKNOWN  127.0.0.1/8
eth0@if24  UP    172.20.0.3/16
 api-debug  ~  ss -ltnp
LISTEN 0 4096 127.0.0.1:8080  ...
```

This output exposes a classic bug: the app listens on `127.0.0.1:8080`, so no other container (and no published port) can ever reach it. Fix the app to bind `0.0.0.0`. To also see the target's process list or mounts, add `--pid container:api` (requires a compatible security context) or use `docker debug api` where Docker Desktop/Pro tooling is available.

### 5.3 DNS Checks

```bash
docker exec web getent hosts api
docker run --rm --network appnet nicolaka/netshoot dig +short api
docker run --rm --network appnet nicolaka/netshoot cat /etc/resolv.conf
docker run --rm --network appnet nicolaka/netshoot dig api @127.0.0.11
docker run --rm --network appnet nicolaka/netshoot dig example.com @8.8.8.8
```

```text
172.20.0.3  api
172.20.0.3
nameserver 127.0.0.11
options ndots:0
```

`127.0.0.11` is Docker's embedded resolver on user-defined networks. If internal names fail but external names work, the container is probably on the default `bridge` (no name resolution) or on different networks. If external names fail but internal work, check the daemon's upstream DNS (`dns` in `daemon.json`, host `/etc/resolv.conf`, VPN-injected resolvers).

### 5.4 Connectivity and Port Tests

```bash
docker exec web sh -c 'nc -zv api 8080'        # TCP connect only
docker exec web sh -c 'wget -qO- --timeout=3 http://api:8080/health'
docker run --rm --network container:web nicolaka/netshoot curl -sv --max-time 3 http://api:8080/health
docker run --rm --network container:web nicolaka/netshoot traceroute -n api
```

```text
api (172.20.0.3:8080) open
* Connected to api (172.20.0.3) port 8080
< HTTP/1.1 200 OK
 1  172.20.0.3  0.201 ms
```

Interpretation guide: `Connection refused` is an immediate RST (nothing listening or wrong port); a hang until timeout means a drop (firewall, wrong network, routing); `No route to host` is ARP or routing failure.

### 5.5 Capture Packets

```bash
# Inside the target's namespace, via sidecar
docker run --rm --network container:api nicolaka/netshoot tcpdump -ni eth0 -c 20 'tcp port 8080'

# From the host, enter the container's namespace without a sidecar
PID=$(docker inspect -f '{{.State.Pid}}' api)
sudo nsenter -t "$PID" -n tcpdump -ni eth0 -c 20 icmp

# Host side of the veth: find the bridge and capture there
ip -br link show type bridge
sudo tcpdump -ni br-3f2a1c9d7e11 -c 20 host 172.20.0.3
```

```text
12:01:44.100 IP 172.20.0.2.51522 > 172.20.0.3.8080: Flags [S], seq 1
12:01:44.100 IP 172.20.0.3.8080 > 172.20.0.2.51522: Flags [R.], ack 2
```

A SYN with an immediate RST confirms "connection refused". A SYN with no reply from the destination means the packet never arrived or was dropped; capture on the bridge and on the destination to find the hop where it disappears. Write captures with `-w file.pcap` and open them in Wireshark.

### 5.6 Firewall and NAT Inspection

```bash
sudo iptables -t nat -S DOCKER
sudo iptables -S DOCKER-USER
sudo iptables -S DOCKER-ISOLATION-STAGE-1
sudo nft list ruleset | grep -A5 -i docker
sudo conntrack -L -p tcp --dport 8080 2>/dev/null | head
sudo iptables -t nat -L POSTROUTING -n -v | grep MASQ
```

```text
-A DOCKER ! -i docker0 -p tcp -m tcp --dport 8080 -j DNAT --to-destination 172.17.0.2:80
-N DOCKER-USER
-A DOCKER-USER -j RETURN
```

Check that a DNAT rule exists for the published port, that `DOCKER-USER` (your own rules) is not dropping it, and that `MASQUERADE` covers outbound traffic. If a host firewall tool (`ufw`, `firewalld`) was reloaded, Docker's chains may be flushed; restart the daemon to recreate them. On hosts using nftables, `iptables` may be the `iptables-nft` shim; use whichever view matches the backend ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).

### 5.7 Published Port and Host-Level Checks

```bash
ss -ltnp | grep 8080                      # who owns the host port
curl -sv --max-time 3 http://127.0.0.1:8080/
curl -sv --max-time 3 http://<host-lan-ip>:8080/
docker run --rm --network host nicolaka/netshoot curl -s ifconfig.me
ip route get 172.20.0.3
```

Reaching `127.0.0.1:8080` but not the LAN IP points to a bind address of `127.0.0.1:8080:80` in the `-p` mapping or a host firewall. Port already allocated errors mean another process (or container) owns the host port.

### 5.8 Overlay and Daemon Evidence

```bash
sudo tcpdump -ni eth0 udp port 4789 -c 10         # VXLAN data plane
docker info --format '{{.Swarm.LocalNodeState}} {{.Swarm.NodeAddr}}'
docker events --filter type=network --since 10m
journalctl -u docker --since "10 min ago" | grep -iE "network|dns|iptables|vxlan"
```

For overlay-specific causes (blocked 4789, MTU) see [§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md).

## 6. Production Usage Notes

- **Keep a vetted debug image** (netshoot or an internal equivalent) in your private registry so it is available when the public registry is unreachable.
- **Prefer sidecars over `exec` + package install**; installing tools in a running container changes it, may violate read-only root filesystems ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)), and is lost on restart.
- **Capture narrowly:** always use filters (`host`, `port`), `-c` counts and short durations; unfiltered captures on busy hosts are heavy and may expose sensitive data.
- **Record evidence before remediation:** save `docker inspect`, `ip a`, `iptables-save` and a short pcap before restarting anything.
- **Health checks and logs** often identify a network issue earlier than manual probes ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)); correlate timestamps.
- **Standard runbook:** put the six-step flow from the diagram into your on-call runbook so every responder uses the same order.
- **Docker Desktop:** host-side tools run in the Linux VM (use a privileged `--pid host` container with `nsenter`), and host networking semantics differ from native Linux.

## 7. Security Considerations

- **A debug sidecar is privileged access.** Sharing a network namespace exposes the target's sockets and lets you sniff its traffic; `NET_ADMIN`/`NET_RAW` capabilities are needed for `tcpdump` and routing changes, so grant them only for the session ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).
- **Packet captures contain data**: credentials, tokens, personal data. Treat pcaps as sensitive, store them encrypted, and delete after use.
- **Avoid `--privileged` and `--pid host`** unless the incident truly requires it; prefer `--cap-add NET_ADMIN --cap-add NET_RAW`.
- **Restrict who can run debug images**; ability to attach to a production container's namespace equals ability to read its traffic.
- **Do not leave debug containers running** or mount the Docker socket into them.
- **Firewall experiments** (inserting `iptables` rules to test) can break isolation between networks ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)); make changes in `DOCKER-USER`, record them, and remove them afterwards.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely layer / cause | Check and fix |
|---|---|---|
| `Could not resolve host` for another container | Default bridge, or different networks | `docker network inspect`; attach both to the same user-defined network |
| `Connection refused` to a container IP | App bound to `127.0.0.1`, wrong port | `ss -ltnp` in the namespace; bind `0.0.0.0` |
| Published port refused from LAN, works on localhost | Port bound to `127.0.0.1`, or host firewall | Check `docker port`; use `-p 0.0.0.0:8080:80` or open firewall |
| Timeouts to the internet from containers | Missing MASQUERADE, IP forwarding off, DNS broken, VPN MTU | `sysctl net.ipv4.ip_forward`, `iptables -t nat -S POSTROUTING`, `dig @8.8.8.8` |
| External DNS fails inside containers only | Host resolver is `127.0.0.53` (systemd-resolved) or VPN-only | Set `dns` in `daemon.json` or `--dns`; see [§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md) |
| Everything broke after `ufw`/`firewalld` reload | Docker chains flushed | `systemctl restart docker`; put custom rules in `DOCKER-USER` |
| Large transfers hang, small work | MTU or PMTU black hole | `ping -M do -s 1472`; lower network MTU |
| Container cannot reach host service | Host service bound to loopback; wrong gateway name | Use `host.docker.internal` / `--add-host=host.docker.internal:host-gateway`; bind host service to the bridge IP |
| `address already in use` / `port is already allocated` | Another process or container holds the port | `ss -ltnp`, `docker ps --filter publish=8080` |
| Intermittent failures with several replicas | One unhealthy replica in round-robin | Query each task IP; check health ([§88](../Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)) |

## 9. Best Practices

- Follow the layered method; state the failing layer before changing anything.
- Test from the *client's* namespace, not from your laptop or the host.
- Use a debug sidecar sharing the namespace instead of modifying production images.
- Distinguish DNS, TCP and application failures with three separate commands (`getent`, `nc -zv`, `curl -v`).
- Capture on both ends and the bridge when packets go missing.
- Keep custom firewall rules in `DOCKER-USER`, version-controlled.
- Log the exact commands and outputs in the incident record.
- Prefer healthchecks and structured logs so most problems are found without a shell.

## 10. Common Anti-Patterns / Mistakes

- Restarting containers or the daemon first, losing the failing state.
- Installing `curl`, `ping` or `tcpdump` into production images permanently "for debugging".
- Testing connectivity from the host and concluding the container network is fine.
- Pinging by IP only and never testing DNS, or testing DNS only and never the TCP port.
- Using `ping` as proof of service health; ICMP success says nothing about a TCP listener.
- Flushing `iptables` (`iptables -F`) to "see if the firewall is the problem", which removes Docker's NAT and isolation rules.
- Running `--privileged` debug containers on shared production hosts without cleanup.
- Assuming a `localhost` bind is reachable from other containers.

## 11. Interview Questions

**🎯 Beginner:** _"Container `web` cannot reach container `db` by the name `db`. What do you check first?"_
**Model answer:** First whether both containers are on the same user-defined network (`docker network inspect` or `docker inspect` showing the same network in `NetworkSettings.Networks`). Name resolution via the embedded DNS only works on user-defined networks, not the default `bridge`. Then test resolution inside `web` with `getent hosts db`, then connectivity with `nc -zv db 5432`. If the name resolves but the port refuses, check that `db` listens on `0.0.0.0` and the right port.
_What the interviewer is probing for:_ The user-defined versus default bridge DNS difference and a step-by-step approach.

**🎯 Intermediate:** _"The image has no shell, `ip` or `curl`. How do you debug its networking?"_
**Model answer:** Start a tool-rich container in its network namespace: `docker run --rm -it --network container:<name> nicolaka/netshoot`. It shares interfaces, routes, DNS config and sockets, so `ss -ltnp`, `dig`, `curl` and `tcpdump -i eth0` show exactly what the target sees. Alternatively from the host, read the PID with `docker inspect -f '{{.State.Pid}}'` and run host tools inside the namespace with `nsenter -t PID -n`. This leaves the production image untouched, works with read-only filesystems, and needs only `NET_ADMIN`/`NET_RAW` for captures.
_What the interviewer is probing for:_ Namespace sharing as a technique, and operational hygiene around production images.

**🎯 Senior:** _"After a firewall service reload, new published ports on a host stopped working and containers lost internet access. Explain and resolve."_
**Model answer:** Tools like `firewalld` or `ufw` reload by flushing and rewriting rulesets, which removes Docker-managed chains: the `nat` table's `DOCKER` DNAT rules and `POSTROUTING` MASQUERADE, and the filter chains such as `DOCKER-ISOLATION-*` and `FORWARD` jumps. I would confirm with `iptables -t nat -S` and `iptables -S FORWARD`, then restore by restarting the Docker daemon, which rebuilds them (containers with `--live-restore` keep running). Longer term, put custom policy in `DOCKER-USER`, configure the firewall to coexist with Docker (trusted zone for bridge interfaces in firewalld), and add a post-reload hook or alert. I would also record the incident and add a smoke test that checks a published port and outbound DNS after firewall changes.
_What the interviewer is probing for:_ Understanding of how Docker programs the firewall and how host firewalls interfere.

**🎯 Architect:** _"Design the network-debugging capability for a platform of 500 hosts running regulated workloads. What do you standardize and constrain?"_
**Model answer:** A standard layered runbook, a signed internal debug image mirrored in the private registry, and a controlled access path: engineers request a time-boxed role that allows starting that one image with `--network container:<target>` and only `NET_ADMIN`/`NET_RAW`, with every launch audited. Pcap output goes to an encrypted bucket with a short retention policy; a classification rule prohibits captures of unencrypted regulated data without approval. Proactive observability reduces the need: DNS and TCP-connect probes from each network, conntrack and drop counters in metrics, structured logs with trace IDs, flow logs at the VPC. Firewall rules live in `DOCKER-USER` managed by configuration management and are verified by post-change smoke tests. Production images stay minimal (distroless) because the debug path does not depend on them.
_What the interviewer is probing for:_ Balancing debuggability with least privilege, auditability and data protection at fleet scale.

## 12. Common Misconceptions

- "If the host can reach it, the other container can too." The host and container namespaces have different routes, DNS and firewall paths.
- "`ping` works, so the service is up." ICMP says nothing about a TCP listener or the application.
- "Connection refused and timeout mean the same thing." Refused is an active RST; timeout is a silent drop.
- "I need to install tools in the container." A sidecar in the same namespace avoids that.
- "`iptables -F` is a safe diagnostic." It deletes Docker's NAT and isolation rules until the daemon restarts.
- "`localhost` inside a container is the host." It is the container's own loopback.

## 13. 🔑 Key Takeaways

- Work in layers: running and listening, shared network, DNS, route and port, firewall and NAT, application.
- Read the error: not-resolved, refused and timed-out point to different layers.
- `docker run --network container:<name> nicolaka/netshoot` is the standard way to debug minimal images.
- `nsenter -t <pid> -n` runs host tools inside a container's namespace.
- Check the app binds `0.0.0.0`, not `127.0.0.1`.
- Never flush `iptables` to test; use `DOCKER-USER` for your own rules and restart the daemon if Docker's chains were removed.
- Treat captures and privileged debug containers as sensitive and time-boxed.

## 14. Related Concepts & What's Next

Related: bridges ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), DNS ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), NAT ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), overlays ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), exec and attach ([§28](../Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)), production troubleshooting ([§93](../Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)) and scenario practice ([§102](../Part14/Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md)). Next, [§48](Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md) turns from diagnosing to designing: the standard communication patterns between containers and the host.

**Next Section:** [§48](Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md) — `Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md`
