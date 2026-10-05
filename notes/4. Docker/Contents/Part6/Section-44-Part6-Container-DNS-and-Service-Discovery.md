# Section 44 (Part 6): Container DNS and Service Discovery

## 1. Definition

**Plain language:** On a user-defined network, containers find each other by name. Docker runs a tiny DNS server for each container, and that server answers "what is the IP of `db`?" with the address of the container (or containers) that carry that name or alias.

**Precise definition:** Containers attached to a user-defined network (custom bridge, overlay, macvlan) get an **embedded DNS server** reachable at `127.0.0.11` inside the container's network namespace ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)). Docker writes `nameserver 127.0.0.11` into the container's `/etc/resolv.conf`. The resolver answers names for container names, service names (Compose), and explicit **network aliases** on the networks the querying container shares with the target. Any name it does not own is forwarded to the upstream DNS servers derived from the host (or from `--dns` / `daemon.json`). Containers on the **default bridge** `bridge` ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)) do not get the embedded server: they receive a copy of the host's resolver configuration and cannot resolve each other by name (the legacy `--link` flag is the only name mechanism there).

> 💡 **Tip:** "Service discovery" in plain Docker is just DNS. There is no registry, no health awareness and no caching layer beyond what your application does itself.

## 2. Why This Matters

- Container IPs change on every recreate; names are the only stable contract between services.
- Most "connection refused" and "could not resolve host" incidents in Compose stacks are DNS scoping mistakes (wrong network, default bridge, stale app-level cache).
- Interviews and the DCA exam ask what `127.0.0.11` is, why names fail on the default bridge, and how aliases and round-robin work.
- Understanding resolver forwarding explains slow lookups, corporate-DNS failures and VPN breakage.

## 3. Prerequisites and Dependencies

Requires the network driver model ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)) and the distinction between default and custom bridges ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)). Network namespaces are explained in [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md); the daemon that hosts the DNS logic is described in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), and `daemon.json` DNS keys in [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md). Compose service naming is covered in [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md).

## 4. Architecture / Conceptual Diagram

```text
  Custom bridge "appnet" (172.20.0.0/16)

  ┌──────────────── container: web ────────────────┐
  │ /etc/resolv.conf                               │
  │   nameserver 127.0.0.11   options ndots:0      │
  │ app: connect("db:5432")                        │
  │   │ 1. DNS query "db" -> 127.0.0.11:53         │
  └───┼────────────────────────────────────────────┘
      │ (iptables DNAT inside the container netns redirects
      │  127.0.0.11:53 to a random port owned by dockerd)
      ▼
  ┌────────────── dockerd embedded resolver ───────────────┐
  │ per-network name table (only networks web is on):      │
  │   db   -> 172.20.0.3                                   │
  │   cache, api (alias), web ...                          │
  │ hit  ──► answer A record (172.20.0.3)                  │
  │ miss ──► forward to upstream DNS ──► 10.0.0.2 / 8.8.8.8│
  └────────────────────────────────────────────────────────┘

  Default bridge "bridge":   resolv.conf = copy of host's upstreams
                             (no container-name resolution)
```

- **Scope is per network:** a name resolves only if querier and target share at least one user-defined network.
- **Multiple records:** several containers with the same alias on one network produce several A records, a form of DNS round-robin.
- **Reverse lookups** (PTR) for container IPs are answered for names the resolver knows.
- **Loopback upstreams:** if the host resolver is `127.0.0.53` (systemd-resolved), Docker substitutes the real upstreams from `/run/systemd/resolve/resolv.conf`, because loopback addresses are meaningless inside a container namespace.

## 5. Hands-On

### 5.1 Name Resolution on a Custom Network

```bash
docker network create appnet
docker run -d --name db --network appnet -e POSTGRES_PASSWORD=pw postgres:16-alpine
docker run --rm --network appnet alpine:3.20 sh -c 'cat /etc/resolv.conf; nslookup db'
```

```text
nameserver 127.0.0.11
options ndots:0

Name:   db
Address: 172.20.0.2
```

### 5.2 The Default Bridge Does Not Resolve Names

```bash
docker run -d --name old-db -e POSTGRES_PASSWORD=pw postgres:16-alpine
docker run --rm alpine:3.20 ping -c1 old-db
```

```text
ping: bad address 'old-db'
```

Attach both to a custom network (or use `docker network connect appnet old-db`) and the lookup works.

### 5.3 Network Aliases

```bash
docker run -d --name pg1 --network appnet --network-alias database postgres:16-alpine
docker run --rm --network appnet alpine:3.20 nslookup database
```

Aliases are per network. A container can be known as `db` on one network and `primary` on another.

### 5.4 DNS Round-Robin Across Replicas

```bash
for i in 1 2 3; do
  docker run -d --name web$i --network appnet --network-alias web nginx:1.27-alpine
done
docker run --rm --network appnet alpine:3.20 nslookup web
```

```text
Name:   web
Address: 172.20.0.4
Name:   web
Address: 172.20.0.5
Name:   web
Address: 172.20.0.6
```

The resolver returns all records and rotates their order. Clients that cache the first answer pin to one replica.

### 5.5 Custom Resolvers, Search Domains and Hosts Entries

```bash
docker run --rm --dns 1.1.1.1 --dns-search corp.example alpine:3.20 cat /etc/resolv.conf
docker run --rm --add-host api.internal:10.0.0.50 alpine:3.20 getent hosts api.internal
docker run --rm --hostname probe --network appnet alpine:3.20 hostname
```

`--add-host` writes to `/etc/hosts`, which the C library consults before DNS. On a user-defined network `--dns` still points `resolv.conf` at `127.0.0.11`; the given servers become the embedded resolver's upstreams.

### 5.6 Reaching the Host by Name

```bash
# Docker Desktop provides host.docker.internal automatically.
# On Linux Engine, map it to the bridge gateway:
docker run --rm --add-host host.docker.internal:host-gateway alpine:3.20 getent hosts host.docker.internal
```

### 5.7 Compose: Service Names Are Free

```yaml
services:
  api:
    image: myapi:1.4
    environment:
      DATABASE_URL: postgres://app:pw@db:5432/app
    networks: [backend]
  db:
    image: postgres:16-alpine
    networks:
      backend:
        aliases: [primary-db]
networks:
  backend: {}
```

Compose attaches every service to the project's default network unless `networks:` is specified. Each service is resolvable by its service name, by its container name, and by any declared alias. With `docker compose up --scale api=3`, the name `api` returns three A records ([§39](../Part5/Section-39-Part5-Scaling-Services-with-Compose.md)).

### 5.8 Inspecting and Debugging

```bash
docker inspect web1 --format '{{json .NetworkSettings.Networks.appnet.Aliases}}'
docker exec web1 cat /etc/resolv.conf /etc/hosts
docker exec web1 getent hosts db          # uses libc order: /etc/hosts then DNS
docker run --rm --network appnet nicolaka/netshoot dig +short db @127.0.0.11
```

```text
["web","web1"]
```

## 6. Production Usage Notes

- **Application caching is the usual culprit.** The embedded resolver does not cache aggressively, but runtimes do. The JVM can cache positive lookups forever under a security manager (tune `networkaddress.cache.ttl`), and nginx resolves `proxy_pass` hostnames once at startup unless you set `resolver 127.0.0.11 valid=10s;` and use a variable.
- **Connection pools** keep sockets to old IPs after a dependency is recreated; set max connection lifetime below your deploy cadence.
- **Aliases enable stable contracts:** point apps at `database`, `cache`, `auth`, and let the Compose file decide which container fulfills each.
- **Docker Swarm** adds a virtual IP per service (a single A record, load balanced by IPVS) or `endpoint_mode: dnsrr` for plain round-robin ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)); overlay behavior is in [§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md).
- **Kubernetes does not use this mechanism.** It uses CoreDNS and kube-proxy; only the habit of "call the service by name" carries over.
- **Daemon-wide defaults:** `{"dns": ["10.0.0.2"], "dns-search": ["corp.example"]}` in `daemon.json` applies to new containers and is the right place to fix corporate DNS ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Restart behavior:** the embedded server follows container lifecycle; a stopped container's name stops resolving, a restarted one may get a new IP.

## 7. Security Considerations

- **Name scope is a boundary.** Only containers sharing a network can resolve (and normally reach) each other, so segmentation by network also segments discovery ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)). Do not attach a front-end container to a backend network just for convenience.
- **Aliases are not authenticated.** Any container allowed to join a network can claim an alias such as `db` and receive traffic meant for the real one. Restrict who may run containers on shared networks and use TLS with certificate verification between services.
- **`/etc/hosts` and `--add-host`** override DNS silently; audit them in images that talk to payment or identity endpoints.
- **Exfiltration over DNS:** the resolver forwards unknown names to the internet. `--internal` networks have no external route, but egress policy for default networks needs host firewall rules ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).
- **Spoofing risk with custom `--dns`:** pointing containers at untrusted resolvers lets them redirect traffic; set resolvers centrally in `daemon.json`.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `could not resolve host: db` between two `docker run` containers | Both on the default bridge | Create a user-defined network and attach both |
| Works in Compose, fails from a one-off `docker run` | Container not on the Compose project network | `--network <project>_default` |
| Name resolves but connect fails | Wrong port or app bound to `127.0.0.1` inside target | Bind to `0.0.0.0`; use the container port, not the published one |
| External names fail, internal names work | Upstream DNS unreachable from container (VPN, corporate DNS) | Set `dns` in `daemon.json` or `--dns`; check `resolv.conf` |
| 5 second delays on lookups | IPv6 `AAAA` timeouts or unreachable first nameserver | Fix upstream, remove dead resolver, disable IPv6 lookups in app |
| Stale IP after dependency redeploy | App or proxy caches resolution | Short TTL/`resolver` directive, restart client, shorter pool lifetime |
| Host loopback resolver (`127.0.0.53`) copied in | Custom setup bypassing Docker's substitution | Use real upstreams; check `/run/systemd/resolve/resolv.conf` |
| `host.docker.internal` unknown on Linux | Only Docker Desktop defines it | `--add-host host.docker.internal:host-gateway` |
| Alias resolves to wrong container | Two containers claimed the same alias | `docker network inspect`, remove the duplicate |

## 9. Best Practices

- Always use user-defined networks; treat the default bridge as legacy.
- Address services by name or alias, never by IP.
- Give each logical dependency a stable alias and keep it identical across environments.
- Put front ends and databases on separate networks; share only what is required.
- Configure upstream DNS once in `daemon.json`, not per container.
- In nginx and similar proxies, configure a resolver with a short `valid=` so replicas are re-discovered.
- Test with `getent hosts` (libc path) as well as `nslookup`/`dig`, since applications use libc.

## 10. Common Anti-Patterns / Mistakes

- Hard-coding container IPs or relying on `docker inspect` output in scripts.
- Using `--link` in new setups.
- Expecting DNS round-robin to behave as health-aware load balancing; dead replicas stay in the answer set until they are removed.
- Mounting a host `resolv.conf` into containers and breaking the embedded resolver.
- Using the published host port in a container-to-container URL instead of the container port.
- Publishing a database port just so another container can reach it.
- Assuming names resolve across different networks or different Compose projects.

## 11. Interview Questions

**🎯 Beginner:** _"Two containers started with plain `docker run` cannot reach each other by name. Why, and what is the fix?"_
**Model answer:** Without `--network`, both attach to the default bridge, which has no embedded DNS server. Name resolution only exists on user-defined networks. The fix is `docker network create appnet` and running both containers with `--network appnet`, after which `ping db` works. Alternatively, `docker network connect` can attach running containers. Compose does this automatically by creating a project network.
_What the interviewer is probing for:_ Default bridge versus user-defined network behavior and the existence of the embedded resolver.

**🎯 Intermediate:** _"What is `127.0.0.11` in a container's `resolv.conf`, and how does an external lookup like `github.com` work from there?"_
**Model answer:** It is Docker's embedded DNS endpoint, implemented by `dockerd` and exposed inside the container namespace through NAT rules to a daemon-owned port. Queries for container names, service names and aliases on shared networks are answered from Docker's internal tables. Everything else is forwarded to the upstream servers inherited from the host, or from `--dns` and `daemon.json`. If the host uses a loopback stub such as systemd-resolved, Docker uses the real upstream list, since loopback inside a container points at itself.
_What the interviewer is probing for:_ Knowledge of how internal and external resolution are split and why loopback upstreams are special.

**🎯 Senior:** _"After redeploying the `api` container, the nginx front end still sends traffic to the old IP and returns 502s until it is reloaded. Explain and fix."_
**Model answer:** nginx resolves static `proxy_pass` hostnames only at configuration load, so the old IP is pinned. Docker already updated its table, but nginx never asks again. Fix by using `resolver 127.0.0.11 valid=5s;` and a variable in `proxy_pass` (`set $up http://api:8080; proxy_pass $up;`) so it re-resolves, or by reloading nginx as part of deploys, or by placing a proxy that supports dynamic service discovery (Traefik). Verify with `docker exec nginx getent hosts api` against the actual upstream IP. The same reasoning covers JVM DNS caching and pooled connections.
_What the interviewer is probing for:_ Separating Docker's DNS correctness from client-side caching, with concrete remedies.

**🎯 Architect:** _"Design service discovery for a 40-service Compose-based environment on a single host with strict segmentation, and explain when you would leave DNS-based discovery behind."_
**Model answer:** Create one network per trust zone (edge, app, data) and attach each service only to the zones it needs; the reverse proxy sits on edge and app, databases only on data with `internal: true`. Use aliases as the stable contract (`auth`, `orders-db`) and keep service names environment-independent. Document that cross-zone calls go through explicit gateway services. DNS round-robin gives rough balancing for stateless replicas but has no health checking, so pair it with HEALTHCHECK-driven restarts and a proxy for anything latency sensitive. I would leave pure DNS discovery when I need multi-host scheduling, health-aware routing, weighted rollouts or mTLS identity, which means Swarm's VIPs or Kubernetes Services plus a mesh or ingress.
_What the interviewer is probing for:_ Using networks as segmentation and discovery boundaries, and recognizing DNS limits.

## 12. Common Misconceptions

- "Containers can always resolve each other by name." Only on user-defined networks, and only if they share one.
- "Container names are globally unique DNS names." They are scoped per daemon and per shared network.
- "DNS round-robin balances load evenly and avoids dead replicas." It does neither reliably.
- "`--link` is how you do service discovery." It is legacy and unnecessary on custom networks.
- "Docker's DNS server caches for the application." The application or runtime cache is what hides changes.

## 13. 🔑 Key Takeaways

- User-defined networks provide an embedded DNS server at `127.0.0.11`; the default bridge does not.
- Resolution is scoped to shared networks and covers names, service names and aliases.
- Unknown names are forwarded to upstream DNS taken from the host, `--dns` or `daemon.json`.
- Several containers with one alias yield several A records (round-robin without health checks).
- Most stale-address problems are client-side caching, not Docker.
- Use container ports and names between containers; published ports are for outside traffic.

## 14. Related Concepts & What's Next

Related: network drivers ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), custom bridges ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), overlay discovery ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), DNS tooling ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), container-to-host patterns ([§48](Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md)), Compose networking ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)). Next, [§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md) shows how traffic from outside the host reaches those containers.

**Next Section:** [§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md) — `Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md`
