# Section 48 (Part 6): Container-to-Host and Container-to-Container Communication Patterns

## 1. Definition

**Plain language:** Containers rarely live alone. This section is the catalogue of ways a container talks to its neighbours and to the machine it runs on: over a shared user-defined network by name, through a published port, via the host's gateway address, through a shared network namespace, over a Unix socket on a shared volume, or through shared memory and files.

**Precise definition:** A communication pattern is a combination of (a) an addressing method (service name, container IP, host gateway name, `localhost`), (b) a transport (TCP/UDP across a bridge, loopback inside a shared namespace, `AF_UNIX` socket on a mounted path, shared IPC), and (c) a boundary being crossed (container to container on one network, container to host, host to container, or container to a different host). The Docker-specific building blocks are user-defined bridge networks and embedded DNS ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md), [§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), port publishing ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), `--network container:<name>`, `--network host`, `--add-host host.docker.internal:host-gateway`, and `--ipc`.

> 💡 **Tip:** Pick the narrowest pattern that works. Same network and a service name is almost always enough; reach for host networking or a shared socket only when you can say why.

## 2. Why This Matters

- "Connection refused" between containers is the most common Docker support question, and it is nearly always one of five causes: wrong network, wrong name, wrong port, `localhost` misunderstanding, or a service bound to `127.0.0.1`.
- Reaching a database or API running on the developer's host (not in a container) behaves differently on Docker Desktop, Linux Engine and rootless mode, so portable Compose files need a deliberate pattern.
- Each pattern changes the attack surface: a published port is reachable from the LAN, a mounted Docker socket is root on the host, a shared network namespace removes isolation between the two containers.
- Sidecars (log shippers, proxies, debuggers) depend on the namespace-sharing patterns; knowing them is a prerequisite for Kubernetes pods ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).

## 3. Prerequisites and Dependencies

You need the network drivers ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), the difference between the default and user-defined bridges ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), embedded DNS ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), and how publishing works ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)). Namespaces are the underlying mechanism ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)). Compose automates most of the container-to-container wiring ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)). When something does not connect, the tool set is in [§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md).

## 4. Architecture / Conceptual Diagram

```text
                          HOST (Linux Engine)
 ┌──────────────────────────────────────────────────────────────────────┐
 │  host process :5432          docker0 / br-xxxx   172.18.0.1 (gateway)│
 │       ▲                            ▲   ▲                             │
 │       │ (E) host-gateway           │   │                             │
 │       │                            │   │                             │
 │  ┌────┴─────────────────────────────┴───┴─────────────────────────┐  │
 │  │ user-defined bridge "appnet"  172.18.0.0/16                    │  │
 │  │                                                                │  │
 │  │  ┌──────────┐ (A) name:port  ┌──────────┐                      │  │
 │  │  │  web     │ ──────────────►│  api     │                      │  │
 │  │  │ 172.18.0.2│               │172.18.0.3│                      │  │
 │  │  └──────────┘                └────┬─────┘                      │  │
 │  │                                   │ (B) shared netns           │  │
 │  │                             ┌─────┴──────┐                     │  │
 │  │                             │ sidecar    │ localhost:8080      │  │
 │  │                             │ --network  │                     │  │
 │  │                             │ container:api                    │  │
 │  │                             └────────────┘                     │  │
 │  └────────────────────────────────────────────────────────────────┘  │
 │      ▲ (C) -p 8080:80 (DNAT)                                         │
 │      │                                                               │
 │  (D) /run/app/app.sock  ◄── bind-mounted into api and proxy          │
 └──────┼───────────────────────────────────────────────────────────────┘
        │
   LAN / internet client
```

| Pattern | Addressing | Crosses | Typical use |
|---|---|---|---|
| A. Same user-defined network | service/container name | container to container | app tiers |
| B. Shared network namespace | `localhost` | container to container | sidecars, debugging |
| C. Published port | `host-ip:published-port` | outside to container | ingress, host to container |
| D. Unix socket on shared volume | file path | container to container or host | proxy to app server, DB sockets |
| E. Host gateway | `host.docker.internal` | container to host | reach host services |
| F. Host network | host's own interfaces | container is the host | performance, many ports |

## 5. Hands-On

### 5.1 Pattern A: Name-Based Container-to-Container

```bash
docker network create appnet
docker run -d --name api --network appnet --network-alias backend nginx:1.27-alpine
docker run --rm --network appnet curlimages/curl -sI http://api
docker run --rm --network appnet curlimages/curl -sI http://backend
```

```text
HTTP/1.1 200 OK
Server: nginx/1.27.x
...
```

Both the container name and the alias resolve through the embedded DNS server at 127.0.0.11 ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)). No port was published; none was needed. Use the **container port** (80) here, never the published one.

### 5.2 The `localhost` Trap and the Bind-Address Trap

```bash
docker run --rm --network appnet curlimages/curl -s --max-time 2 http://localhost:80 || echo "no listener on MY localhost"
```

```text
no listener on MY localhost
```

Inside a container, `localhost` is that container's own loopback. A second, separate trap is a server bound to `127.0.0.1` inside its own container: other containers cannot reach it even on the same network. The fix is to bind `0.0.0.0` (for example `flask run --host 0.0.0.0`, or `listen 0.0.0.0:3000`).

```bash
docker exec api ss -ltnp          # look at the Local Address column: 0.0.0.0:80 vs 127.0.0.1:80
```

### 5.3 Pattern B: Sharing a Network Namespace (Sidecar)

```bash
docker run -d --name api2 nginx:1.27-alpine
docker run --rm --network container:api2 curlimages/curl -sI http://localhost
```

```text
HTTP/1.1 200 OK
```

The sidecar has no network of its own; it uses `api2`'s namespace, so `localhost:80` is the other container's nginx. Both see the same interfaces, IP, routing table and port space (a port conflict between them is an error). Compose spells it `network_mode: "service:api"`. This is the exact model Kubernetes pods use: a pause container holds the namespace and the app containers join it.

A common debugging use is attaching a tools image to a distroless container that has no shell:

```bash
docker run --rm -it --network container:api2 --pid container:api2 nicolaka/netshoot
```

### 5.4 Pattern C: Published Ports, Host to Container

```bash
docker run -d --name web -p 127.0.0.1:8080:80 nginx:1.27-alpine
curl -sI http://127.0.0.1:8080
```

```text
HTTP/1.1 200 OK
```

Binding the host side to `127.0.0.1` keeps the service off the LAN. The unqualified `-p 8080:80` binds `0.0.0.0` and is reachable from other machines ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)). Containers on the same network never need the published port to reach each other.

### 5.5 Pattern E: Container to a Service on the Host

On Docker Desktop, `host.docker.internal` resolves automatically. On Linux Engine you add it yourself (Engine 20.10+):

```bash
python3 -m http.server 9000 --bind 0.0.0.0 &     # a host service
docker run --rm --add-host host.docker.internal:host-gateway curlimages/curl -sI http://host.docker.internal:9000
```

```text
HTTP/1.0 200 OK
Server: SimpleHTTP/0.6 Python/3.12
```

`host-gateway` is a special value that the daemon replaces with the host's address on the bridge (usually 172.17.0.1). In Compose:

```yaml
services:
  app:
    image: myapp:1.0
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

The host service must listen on an address the bridge can reach (`0.0.0.0` or the bridge IP), and the host firewall must allow traffic from the bridge subnet to that port. A service bound only to `127.0.0.1` on the host is unreachable from a bridged container. In rootless mode the gateway is provided by the user-space network stack (slirp4netns or pasta) and `host.docker.internal` may need the `--add-host` form and the `slirp4netns` "allow host loopback" option.

### 5.6 Pattern D: Unix Socket on a Shared Volume

```bash
docker volume create sockets
docker run -d --name app --user 1000:1000 -v sockets:/run/app myapp:1.0     # app listens on /run/app/app.sock
docker run -d --name proxy -p 8080:80 -v sockets:/run/app:ro \
  -v "$PWD/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine
```

```nginx
upstream app { server unix:/run/app/app.sock; }
server { listen 80; location / { proxy_pass http://app; } }
```

A socket removes TCP, ports and the network from the picture, so it works even with `--network none`. Both containers must run on the same host and agree on the file ownership and mode of the socket.

### 5.7 Pattern F: Host Networking

```bash
docker run --rm --network host nginx:1.27-alpine nginx -t
docker run -d --network host --name hostweb nginx:1.27-alpine      # listens directly on host :80
```

The container shares the host's network namespace: no NAT, no per-container IP, `-p` is ignored, and every listening port is a host port. On Linux this is straightforward. On Docker Desktop, host networking is supported in recent versions only when enabled in settings and applies to the Desktop VM's network, not the Windows or macOS host; do not rely on it there.

### 5.8 Shared IPC and Shared Volumes for Data

```bash
docker run -d --name producer --ipc shareable myapp-producer
docker run -d --name consumer --ipc container:producer myapp-consumer
docker run --rm -v shared:/data alpine sh -c 'echo hello > /data/msg'
docker run --rm -v shared:/data:ro alpine cat /data/msg
```

```text
hello
```

`--ipc` shares System V IPC and POSIX shared memory (`/dev/shm`) for high-throughput producer/consumer pairs. A shared volume is the simplest file-based exchange ([§30](../Part4/Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md)).

## 6. Production Usage Notes

- **Default to Pattern A.** One user-defined network per application, one service name per tier, container ports in connection strings. Put the database on a network that only the API joins ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- **Do not hard-code container IPs.** They change on recreate. Use names, aliases, or `--ip` with a fixed subnet only for rare legacy needs.
- **Compose service names** are DNS names on the project's default network; `container_name:` is optional and prevents scaling ([§39](../Part5/Section-39-Part5-Scaling-Services-with-Compose.md)).
- **Readiness is not reachability.** A name resolving does not mean the service accepts connections; use health checks and `depends_on: condition: service_healthy` ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)) and client retries.
- **Container to host in production** is a smell. Prefer putting the dependency in a container, or reach it by its real DNS name or IP. Keep `host.docker.internal` for developer machines.
- **Host networking** is justified for high packet rates, large port ranges (RTP, passive FTP) or monitoring agents; accept that port conflicts and lost isolation come with it.
- **Cross-host traffic** needs published ports plus a load balancer, or overlay networks ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)); plain bridges are single-host.
- **Sockets** win for same-host proxy-to-app hops: lower latency, no exposed port, and file permissions as access control.

## 7. Security Considerations

- **Every published port widens exposure.** Bind to `127.0.0.1` or a specific interface unless the service must face the LAN. Docker's iptables rules bypass `ufw`/`firewalld` input rules for published ports on classic setups, so a "blocked" port can still be open ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).
- **Mounting `/var/run/docker.sock` into a container is equivalent to root on the host.** Any process with the socket can start a privileged container. Avoid it, or front it with a filtered socket proxy that allows only the needed API calls ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **`--network host` removes the network boundary:** the container can reach services bound to host loopback (databases, metadata endpoints, admin ports) and sniff host-visible traffic with the right capabilities.
- **Shared namespaces trust the partner.** With `container:` networking or `--pid container:`, a compromise of one container is a compromise of the other's network view and processes.
- **`host.docker.internal` is a path into the host.** A compromised container can scan and attack any host service listening on the bridge address, including ones assumed to be "local only". Firewall the bridge subnet to the specific host ports required.
- **Same-network trust is flat by default:** every container on a bridge can reach every other. Segment by network ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- **Sockets:** set ownership and mode (`0660`) deliberately, never `0777`, and mount read-only on the client side where the protocol allows.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `could not translate host name "db"` / `Name or service not known` | Containers on different networks, or on the default bridge (no DNS by name) | Put both on the same user-defined network; check `docker inspect -f '{{json .NetworkSettings.Networks}}'` |
| `connection refused` to `api:3000` while `curl localhost:3000` works inside `api` | Server bound to `127.0.0.1` in its container | Bind `0.0.0.0` |
| Works from host via `localhost:8080`, fails container to container on `8080` | Using the published port instead of the container port | Use `api:80` (container port) |
| App uses `localhost:5432` for a database in another container | `localhost` is the container itself | Use the service name; or `network_mode: service:db` if truly co-located |
| `host.docker.internal` not found on Linux | Name only auto-defined on Docker Desktop | `--add-host host.docker.internal:host-gateway` |
| Host service reachable from host but not from container | Host service bound to `127.0.0.1`, or firewall drops the bridge subnet | Bind `0.0.0.0`/bridge IP; allow `172.x.0.0/16` to the port |
| `Address already in use` after `--network host` | Host port taken by another process | Free the port, or use a bridge with `-p` |
| Sidecar cannot start: `No such container` | Target container not running or not created first | Start the target first; use `depends_on` with `network_mode: service:` |
| Unix socket `Permission denied` | UID/GID mismatch across containers | Align `--user`, group-write the socket, or use a shared GID |
| Intermittent failures right after `up` | Dependency not ready yet | Healthchecks plus retry with backoff |

## 9. Best Practices

- One user-defined network per application; use service names and container ports.
- Bind servers to `0.0.0.0` inside containers and restrict exposure with the publish flag, not the app bind address.
- Publish only the edge service, and bind it to a specific host interface when possible.
- Treat `host.docker.internal` as a developer convenience; make it a Compose override file, not the base file ([§38](../Part5/Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)).
- Add client-side retries, timeouts and health checks; never assume start order equals readiness.
- Use `network-alias` for stable logical names (`db`, `cache`) that decouple code from container names.
- Prefer sockets or shared volumes only for same-host, tightly coupled pairs, and document the ownership contract.
- Keep a debugging container (netshoot) ready to join a target's namespace ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)).

## 10. Common Anti-Patterns / Mistakes

- Hard-coding container IPs (`172.17.0.3`) in configs.
- Using the legacy `--link` flag; user-defined networks replace it.
- Putting every service on the default bridge and relying on published ports for internal traffic, which sends internal calls through NAT and exposes them to the LAN.
- Publishing a database port (`-p 5432:5432`) for convenience and leaving it on `0.0.0.0` in production.
- Mounting the Docker socket into an application container "to list containers".
- Using `--network host` to dodge a DNS or port misconfiguration instead of fixing it.
- Pointing production containers at `host.docker.internal` for a database.
- Running two processes that need `localhost` coupling in separate containers on different networks, then patching with `extra_hosts`.
- Using `container_name:` for every service, which blocks `--scale` and creates cross-project collisions.

## 11. Interview Questions

**🎯 Beginner:** _"You have a `web` container and a `db` container. How does `web` reach `db`, and which port does it use?"_
**Model answer:** Put both on the same user-defined bridge network (Compose does this automatically per project). Docker's embedded DNS resolves the service name `db` to the container's IP, and `web` connects to `db:5432`, the container's own port. No `-p` publishing is needed for container-to-container traffic; publishing is only for traffic coming from outside the Docker network, such as your browser on the host. On the default `bridge` network name resolution does not work, which is why user-defined networks are recommended.
_What the interviewer is probing for:_ Service-name resolution on user-defined networks and the container-port versus published-port distinction.

**🎯 Intermediate:** _"Your app container must call an API running on the developer's laptop at port 9000. It works on Docker Desktop but fails on a Linux CI runner. Why, and how do you make it portable?"_
**Model answer:** `host.docker.internal` is defined automatically by Docker Desktop, but not by Linux Engine. On Linux you map it with `--add-host host.docker.internal:host-gateway` (or `extra_hosts` in Compose), which the daemon resolves to the host's bridge gateway address. Then the host service must be listening on an address reachable from that bridge, not only `127.0.0.1`, and the host firewall must allow the bridge subnet. For portability I would put the mapping in a Compose override used for development and, in CI, run the dependency as a container on the shared network instead of reaching back to the host.
_What the interviewer is probing for:_ Platform differences, the `host-gateway` mechanism, and knowing that bind address and firewall also matter.

**🎯 Senior:** _"Two services must talk over `localhost` because a legacy component hard-codes it, and you also need to attach a debugger sidecar to a distroless container. What are your options and the trade-offs?"_
**Model answer:** Share a network namespace: `--network container:<target>` or Compose `network_mode: "service:<target>"`. The partner sees the target's interfaces, IP and port space, so `localhost` works and a debug image such as netshoot can run `tcpdump`, `ss` and `curl` against a shell-less target; adding `--pid container:<target>` also exposes its processes. The trade-offs: the two containers are now coupled (port conflicts, shared lifecycle ordering, the target must exist first), isolation between them is gone so a compromise of either is shared, and you cannot publish ports on the sidecar, only on the owner. This is the same model as a Kubernetes pod, and I would use it intentionally for tight pairs and ephemeral debugging only.
_What the interviewer is probing for:_ Namespace sharing mechanics, lifecycle coupling, and security consequences.

**🎯 Architect:** _"Design the communication model for a platform where most services are on one host today but will be split across hosts later, and some workloads need low-latency IPC with a local proxy. What do you standardize?"_
**Model answer:** Standardize on name-based addressing so that location is a deployment detail: services use stable DNS names and container ports, never IPs or `localhost` assumptions across containers. On one host that is a per-application user-defined network, with only edge services publishing ports bound to specific interfaces. For multi-host, the same names are served by overlay networking or an orchestrator's service discovery and a load balancer, so application configuration does not change. Reserve Unix sockets over shared volumes for same-host proxy-to-app hops where latency matters, and wrap them behind a named interface so they can be replaced by TCP when a workload moves. Ban host-gateway use and socket mounts in production policy, enforce with admission checks or CI linting of Compose and manifests, and require health checks and client retries so ordering assumptions do not leak into the topology.
_What the interviewer is probing for:_ Location-independent design, a migration path to multi-host, and policy-level enforcement of risky patterns.

## 12. Common Misconceptions

- "Containers need `-p` to talk to each other." They do not; publishing is for outside access.
- "`localhost` inside a container reaches the host." It reaches the container itself.
- "`--network host` works the same on Docker Desktop as on Linux." It does not share the Windows or macOS host's stack.
- "Using the container name works on every network." Only on user-defined networks, not the default bridge.
- "A name that resolves means the service is up." DNS resolves as soon as the container exists on the network.
- "Binding `127.0.0.1` in the app is a safe default in containers." It makes the service unreachable from peers; restrict exposure at the publish layer instead.

## 13. 🔑 Key Takeaways

- Same user-defined network plus service name plus container port is the default pattern.
- `localhost` is per network namespace; sidecars share it with `--network container:`.
- Reach the host with `host.docker.internal:host-gateway` on Linux, and ensure the host service is not loopback-only.
- Publish only edge ports, bound to a specific host interface.
- The Docker socket, `--network host` and shared namespaces trade isolation for convenience; use them knowingly.
- Resolution is not readiness; add health checks and retries.

## 14. Related Concepts & What's Next

Related: network drivers ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), bridges ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), DNS ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), port publishing ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), overlays ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), troubleshooting ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), Compose networking ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), and Docker socket trade-offs ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)). Next, [§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md) turns these patterns into a security design: isolating tiers, restricting egress and hardening published services.

**Next Section:** [§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md) — `Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md`
