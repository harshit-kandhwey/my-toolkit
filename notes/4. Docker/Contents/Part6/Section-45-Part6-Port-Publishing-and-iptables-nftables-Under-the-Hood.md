# Section 45 (Part 6): Port Publishing and iptables/nftables Under the Hood

## 1. Definition

**Plain language:** A container lives on a private network inside the host. Publishing a port (`-p 8080:80`) tells Docker to make host port 8080 forward to container port 80, so outside clients can reach the service.

**Precise definition:** `docker run -p [HOST_IP:]HOST_PORT:CONTAINER_PORT[/proto]` creates a mapping implemented by the daemon in two parts: **kernel packet rules** (iptables, or nftables on newer releases) that DNAT inbound traffic to the container IP, plus MASQUERADE rules for outbound traffic, and an optional **userland proxy** (`docker-proxy`) process that handles cases the kernel rules cannot, such as hairpin and some loopback traffic. `EXPOSE` in a Dockerfile ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)) is only metadata; `-P` publishes every exposed port to a random high host port.

> 💡 **Tip:** Publishing without a host IP binds to all interfaces (`0.0.0.0` and `[::]`). That is the single most common way databases end up on the public internet.

## 2. Why This Matters

- Published ports are the host's attack surface; understanding the rules explains why a firewall like UFW does not protect them by default.
- Debugging "works inside the host but not from outside" requires knowing which chain drops the packet.
- DCA and interview questions ask where Docker inserts rules and what `DOCKER-USER` is for.
- Performance and source-IP behavior (client address lost behind the proxy or NAT) depend on the mechanism.

## 3. Prerequisites and Dependencies

Requires the bridge model ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), network namespaces and veth pairs ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md)), and the daemon's role ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). Name-based discovery is in [§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md). Daemon switches such as `iptables`, `ip` and `userland-proxy` live in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

## 4. Architecture / Conceptual Diagram

```text
 Client 203.0.113.9 ──► host eth0 :8080
                            │
   raw/PREROUTING ► mangle ► nat/PREROUTING
                            │  -m addrtype --dst-type LOCAL -j DOCKER
                            ▼
                     nat/DOCKER chain
                     DNAT tcp dpt:8080 ► 172.17.0.2:80
                            │
                routing decision: dest 172.17.0.2 is not local
                            │
                            ▼
                     filter/FORWARD
                       ├─ DOCKER-USER      (your rules, evaluated first)
                       ├─ DOCKER-FORWARD / DOCKER-ISOLATION (inter-network drops)
                       └─ DOCKER           (ACCEPT only published ports to containers)
                            │
                            ▼
                  docker0 / br-xxxx ──► veth ──► container eth0 :80

 Reply path: conntrack reverses the DNAT automatically.
 Outbound from container: nat/POSTROUTING
   -s 172.17.0.0/16 ! -o docker0 -j MASQUERADE   (source becomes host IP)

 Host-local client 127.0.0.1:8080: nat/OUTPUT ► DOCKER chain (DNAT),
 with docker-proxy as fallback when the userland proxy is enabled.
```

- **Chains Docker manages:** `nat` table `DOCKER`; `filter` table `DOCKER`, `DOCKER-USER`, isolation chains (Docker 28 groups forwarding logic under `DOCKER-FORWARD`, older releases used `DOCKER-ISOLATION-STAGE-1/2`).
- **DOCKER-USER** is the only place guaranteed to be evaluated before Docker's own accept rules and not overwritten on restart.
- **conntrack** tracks each flow, so no per-packet state is kept by Docker itself.
- **Newer releases** add an nftables firewall backend (introduced as experimental in the 29 line); the concepts (DNAT, masquerade, per-network isolation, a user-controlled hook) map one to one.

## 5. Hands-On

### 5.1 Publishing Syntax Variants

```bash
docker run -d --name w1 -p 8080:80 nginx:1.27-alpine                 # all interfaces
docker run -d --name w2 -p 127.0.0.1:8081:80 nginx:1.27-alpine       # loopback only
docker run -d --name w3 -p 8082:80/tcp -p 5353:53/udp nginx:1.27-alpine
docker run -d --name w4 -p 9000-9002:9000-9002 nginx:1.27-alpine     # range
docker run -d --name w5 -p 80 nginx:1.27-alpine                      # random host port
docker run -d --name w6 -P nginx:1.27-alpine                         # all EXPOSEd ports
docker port w1
```

```text
80/tcp -> 0.0.0.0:8080
80/tcp -> [::]:8080
```

### 5.2 Looking at the NAT Rules

```bash
sudo iptables -t nat -S DOCKER
sudo iptables -t nat -S POSTROUTING | grep -i masq
```

```text
-N DOCKER
-A DOCKER -i docker0 -j RETURN
-A DOCKER ! -i docker0 -p tcp -m tcp --dport 8080 -j DNAT --to-destination 172.17.0.2:80
-A POSTROUTING -s 172.17.0.0/16 ! -o docker0 -j MASQUERADE
```

The `! -i docker0` match keeps traffic originating inside the bridge from being re-DNATed.

### 5.3 Looking at the Filter Rules

```bash
sudo iptables -S DOCKER
sudo iptables -S DOCKER-USER
sudo iptables -S FORWARD
```

```text
-A DOCKER -d 172.17.0.2/32 ! -i docker0 -o docker0 -p tcp -m tcp --dport 80 -j ACCEPT
-A DOCKER-USER -j RETURN
-A FORWARD -j DOCKER-USER
```

Only the container-side port (80) is accepted for forwarding; unpublished ports stay closed even though the container is reachable from the host.

### 5.4 The Userland Proxy

```bash
ps aux | grep docker-proxy
```

```text
root  4121  /usr/bin/docker-proxy -proto tcp -host-ip 0.0.0.0 -host-port 8080 -container-ip 172.17.0.2 -container-port 80
```

`docker-proxy` holds the host port open (so no other process can bind it) and relays connections that did not traverse the kernel DNAT path. Disable it with `"userland-proxy": false` in `daemon.json` to rely on kernel rules only; this saves one process per port and preserves client source addresses for local traffic.

### 5.5 Restricting Exposure

```bash
# Bind a database to loopback and reach it through an SSH tunnel or local tools
docker run -d --name pg -e POSTGRES_PASSWORD=pw -p 127.0.0.1:5432:5432 postgres:16-alpine

# Default for all future -p without an IP, set in /etc/docker/daemon.json
# { "ip": "127.0.0.1" }
```

### 5.6 Filtering Published Ports with DOCKER-USER

UFW and firewalld INPUT rules do not see forwarded (DNATed) traffic. Put restrictions in `DOCKER-USER`, matching the original destination port with conntrack because DNAT has already happened:

```bash
# Allow only 203.0.113.0/24 to reach published ports on eth0
sudo iptables -I DOCKER-USER -i eth0 ! -s 203.0.113.0/24 -m conntrack --ctorigdstport 8080 --ctdir ORIGINAL -j DROP
sudo iptables -S DOCKER-USER
```

```text
-A DOCKER-USER -i eth0 ! -s 203.0.113.0/24 -p tcp -m conntrack --ctorigdstport 8080 --ctdir ORIGINAL -j DROP
-A DOCKER-USER -j RETURN
```

Persist rules with your distribution's mechanism (netfilter-persistent, a systemd unit ordered after `docker.service`), because Docker recreates its own chains on start but leaves `DOCKER-USER` contents intact.

### 5.7 Compose Equivalent

```yaml
services:
  web:
    image: nginx:1.27-alpine
    ports:
      - "127.0.0.1:8080:80"        # short syntax
      - target: 443                # long syntax
        published: "8443"
        host_ip: 0.0.0.0
        protocol: tcp
    expose: ["9113"]               # container-only, no host publication
```

### 5.8 Verifying Reachability Layer by Layer

```bash
curl -sI http://127.0.0.1:8080 | head -1                      # host path
curl -sI http://$(docker inspect -f '{{.NetworkSettings.IPAddress}}' w1):80 | head -1   # direct to container (Linux host)
sudo conntrack -L 2>/dev/null | grep 8080                      # live translated flows
sudo iptables -t nat -L DOCKER -n -v                           # packet counters per rule
```

## 6. Production Usage Notes

- **Publish only what must be public.** Put a reverse proxy (nginx, Traefik, Caddy) on 80/443 and keep every other service on internal networks reachable only by name ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)).
- **Loopback binding** (`127.0.0.1:port`) is the default for admin ports, metrics and databases on shared hosts.
- **Source IP:** with bridge networking and the userland proxy, local clients can appear as the gateway address (`172.17.0.1`). Behind external traffic, the kernel DNAT path preserves the client IP; verify before relying on IP allow-lists. `--network host` avoids NAT entirely at the cost of isolation ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)).
- **Port conflicts** are first-come: the host port is bound at `docker run`, not at container listen time.
- **Recent Engine releases** (28+) block direct routed access from other L2 hosts to unpublished container ports on bridge networks, closing the "publish nothing yet reachable" gap that older versions had.
- **`"iptables": false`** stops Docker from managing rules; then you own masquerade, forwarding and DNAT entirely. Only for environments with a mature firewall pipeline.
- **IPv6:** enable with `"ipv6": true` and a `fixed-cidr-v6`; recent Engine versions can publish to IPv6 without NAT66 hacks, but verify firewall policy for the new family.
- **Kubernetes** uses kube-proxy and CNI instead; `-p` semantics do not carry over ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).

## 7. Security Considerations

- **UFW/firewalld bypass:** Docker inserts rules ahead of them in `FORWARD`/`nat`, so `ufw deny 5432` does not block `-p 5432:5432`. Bind to loopback, filter in `DOCKER-USER`, or run Docker with a managed firewall backend.
- **Default-all-interfaces binding** exposes services on every NIC including public ones; set `"ip": "127.0.0.1"` in `daemon.json` and publish publicly on purpose.
- **Unauthenticated services** (Redis, MongoDB, Elasticsearch, Docker's own TCP 2375 API) published to the internet are routinely compromised within minutes.
- **ICC and isolation:** the `DOCKER-ISOLATION` rules drop traffic between different bridge networks; do not disable them casually ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- **Rule drift:** manually flushing iptables (`iptables -F`) breaks Docker networking and can silently remove isolation; restart the daemon to regenerate chains.
- **Privilege:** managing the firewall needs `NET_ADMIN` on the host; containers must never be granted it to edit host rules ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `bind: address already in use` | Host port taken by another process or container | `ss -ltnp \| grep :8080`; choose another port |
| Reachable from host, not from other machines | Bound to `127.0.0.1`, or cloud security group/host firewall in the way | Publish on `0.0.0.0` intentionally; open the right firewall layer |
| Service exposed despite `ufw deny` | Docker's DNAT/FORWARD rules precede UFW | Bind to loopback or filter in `DOCKER-USER` |
| Published port works then breaks after `systemctl restart firewalld` | Firewall reload wiped Docker chains | Restart Docker after firewall reloads |
| Container cannot reach internet | Missing MASQUERADE, `ip_forward` off, `iptables: false` | `sysctl net.ipv4.ip_forward=1`; restart Docker; check POSTROUTING |
| App sees `172.17.0.1` as client IP | Userland proxy or hairpin through bridge | Disable proxy, use host networking, or proxy-protocol/`X-Forwarded-For` |
| Port works for TCP but not UDP | Published without `/udp` | Add `-p 5353:53/udp` |
| `docker port` empty | Port only `EXPOSE`d, not published | Use `-p` or `-P` |
| Rules gone after custom `iptables -F` | Manual flush | Restart `dockerd` to recreate chains |

## 9. Best Practices

- Publish with an explicit host IP; use `127.0.0.1` unless the service must be public.
- Put one reverse proxy in front; keep every other service unpublished.
- Enforce policy in `DOCKER-USER`, persisted across reboots and ordered after Docker starts.
- Set `"ip": "127.0.0.1"` as a safe default on hosts where publishing is the exception.
- Use `ss -ltnp`, `iptables -t nat -L DOCKER -n -v` and `conntrack -L` as standard diagnostics ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)).
- Monitor external exposure with a port scan from outside, not by reading Compose files.
- Document each published port: purpose, protocol, owner.

## 10. Common Anti-Patterns / Mistakes

- Trusting UFW or firewalld to protect published ports.
- `-p 5432:5432` on a database to "let the other container connect" (use the shared network).
- Publishing the Docker API (`-H tcp://0.0.0.0:2375`) without TLS.
- Using `--network host` just to avoid port mappings, losing isolation.
- Hard-coding random host ports from `-P` into clients.
- Flushing iptables to "reset the firewall" on a Docker host.
- Assuming `EXPOSE` opens the port.

## 11. Interview Questions

**🎯 Beginner:** _"What does `-p 8080:80` do, and how is it different from `EXPOSE 80` in a Dockerfile?"_
**Model answer:** `-p 8080:80` publishes the container's port 80 on host port 8080 so external clients can connect to the host and be forwarded to the container; it binds on all interfaces unless a host IP is given. `EXPOSE 80` only records metadata in the image saying the application listens on 80; it opens nothing by itself, though `-P` uses it to choose which ports to publish randomly. Containers on the same user-defined network can reach each other on any listening port without publishing.
_What the interviewer is probing for:_ The metadata versus runtime distinction and understanding that publishing is for outside traffic.

**🎯 Intermediate:** _"Trace what happens, at the iptables level, to a packet arriving at host port 8080 for a published container."_
**Model answer:** In `nat/PREROUTING`, a rule matching local destination addresses jumps to the `DOCKER` chain, where a DNAT rule rewrites destination `host:8080` to `172.17.0.2:80`. Routing then sees a non-local destination and forwards it, so the packet traverses `filter/FORWARD`, which jumps through `DOCKER-USER`, the isolation chains and finally the `DOCKER` chain with an ACCEPT for that container port. The packet leaves via the bridge and veth. Replies are un-NATed by conntrack, and outbound container traffic is masqueraded in `POSTROUTING`. Local clients hit `nat/OUTPUT` or `docker-proxy`.
_What the interviewer is probing for:_ A working mental model of DNAT, forwarding chains and conntrack rather than rote command recall.

**🎯 Senior:** _"Security found Postgres reachable from the internet on a host where UFW denies 5432. How did that happen, and how do you fix it durably?"_
**Model answer:** The container was run with `-p 5432:5432`. Docker's DNAT in `nat/PREROUTING` redirects traffic to the container address, so it flows through the `FORWARD` path where Docker's ACCEPT rules apply; UFW's rules live in `INPUT`, which a forwarded packet never reaches. Immediate fix: republish on `127.0.0.1` or remove the publication and use a shared network. Durable fix: set `"ip": "127.0.0.1"` in `daemon.json`, add allow-list rules in `DOCKER-USER` matching `--ctorigdstport` and `--ctdir ORIGINAL`, persist them, add an external port-scan check in CI/monitoring, and put cloud security groups in front as a second layer.
_What the interviewer is probing for:_ Knowing the INPUT versus FORWARD distinction and applying layered, durable controls.

**🎯 Architect:** _"You must run 60 Compose stacks on shared hosts, each wanting ports 80 and 443, with tenant isolation. Design the exposure model."_
**Model answer:** Never let stacks publish 80/443 directly. Run one shared ingress proxy (Traefik or nginx) bound to the public IPs, attached to a per-tenant network for each stack it fronts; stacks publish nothing and expose services on their private networks, routed by host name and labels with TLS terminated at the proxy. Admin and metrics ports bind to loopback or a management network only. Enforce the policy with `"ip": "127.0.0.1"`, a `DOCKER-USER` default-drop for unexpected ingress, per-tenant networks with `--internal` where egress is unnecessary, a CI check rejecting `ports:` in tenant Compose files, and external scans. For scale beyond the host, move to orchestrator ingress and network policy.
_What the interviewer is probing for:_ Centralizing publishing, preventing port collisions, defense in depth and policy enforcement at build and run time.

## 12. Common Misconceptions

- "`EXPOSE` makes a port reachable." It is documentation only.
- "My host firewall protects containers." Published ports bypass INPUT-based tools like UFW.
- "Docker uses a proxy process for all port traffic." Normally the kernel DNAT does the work; `docker-proxy` is a fallback and port holder.
- "`-p 80:80` binds only to localhost." It binds to all interfaces.
- "Unpublished means unreachable." Containers are reachable from the host and from peers on their networks.
- "Docker's rules persist if I flush iptables." They are recreated only at daemon restart.

## 13. 🔑 Key Takeaways

- Publishing = DNAT in `nat/DOCKER` + ACCEPT in `filter/DOCKER` + MASQUERADE for outbound.
- Default publish address is all interfaces; use `127.0.0.1` or `"ip"` in `daemon.json`.
- UFW/firewalld do not guard published ports; use `DOCKER-USER`.
- `docker-proxy` is optional (`userland-proxy: false`) and mainly affects local/hairpin traffic and source IPs.
- Containers need no published ports to talk to each other on a shared network.
- Keep exposure minimal: one reverse proxy, everything else private.

## 14. Related Concepts & What's Next

Related: network drivers ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), custom bridges ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), DNS ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), `EXPOSE` ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), communication patterns ([§48](Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md)), segmentation ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)), `run` flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)). Next, [§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md) extends networking beyond a single host.

**Next Section:** [§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md) — `Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md`
