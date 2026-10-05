# Section 42 (Part 6): Docker Network Drivers Overview: bridge, host, none, overlay, macvlan

## 1. Definition

**Plain language:** A Docker network driver decides *how a container is wired to the network*: through a private virtual switch on the host (`bridge`), directly onto the host's own network stack (`host`), to nothing at all (`none`), across several hosts (`overlay`), or as a first-class device on your physical LAN (`macvlan`/`ipvlan`).

**Precise definition:** Docker's networking subsystem (libnetwork, part of `dockerd`; see [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)) implements the Container Network Model (CNM): a **sandbox** (a network namespace, [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)) holds one or more **endpoints** (typically one end of a veth pair), each attached to a **network** managed by a **driver**. Built-in drivers are `bridge`, `host`, `none`, `overlay`, `macvlan` and `ipvlan`; third-party drivers can be added through the plugin system. A separate **IPAM driver** hands out subnets and addresses. A container can be attached to several networks at once, and each network is an isolated Layer 2/3 domain.

> 💡 **Tip:** "Which driver?" is really two questions: *who needs to reach this container* (only its neighbours, the host, the LAN, other hosts) and *how much isolation do you want to give up* for performance or addressability.

## 2. Why This Matters

- Every connectivity problem ("it works on my laptop", "service A cannot reach service B") starts with knowing which driver and which network the container is on.
- Driver choice trades isolation for convenience and speed: `host` is fastest and least isolated; `bridge` is the balanced default; `none` is the most locked down.
- Security boundaries between tiers (frontend, backend, database) are built from separate networks ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- Compose, Swarm and Kubernetes (via CNI) all reuse these concepts, so the vocabulary carries over ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md), [§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)).
- Interview and DCA staples: "explain bridge versus host", "what is macvlan for", "why can't containers on the default bridge resolve each other by name".

## 3. Prerequisites and Dependencies

Requires network namespaces and veth pairs ([§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md), [§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), basic IP addressing, subnets and NAT, and the daemon and its configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). Compose network syntax appears in [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md). The next section ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)) takes the `bridge` driver apart in detail; DNS, port publishing and overlay internals have their own sections ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md), [§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md), [§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)).

## 4. Architecture / Conceptual Diagram

```text
                          ONE DOCKER HOST
 ┌───────────────────────────────────────────────────────────────────────────┐
 │  bridge              host               none          macvlan             │
 │ ┌────────┐ ┌────────┐                                ┌────────┐           │
 │ │ ctr A  │ │ ctr B  │  ┌────────┐    ┌────────┐      │ ctr E  │           │
 │ │ eth0   │ │ eth0   │  │ ctr C  │    │ ctr D  │      │ eth0   │           │
 │ └───┬────┘ └───┬────┘  │ (uses  │    │  lo    │      └───┬────┘           │
 │   veth       veth      │ host's │    │  only  │          │ own MAC        │
 │     └────┬─────┘       │ stack) │    └────────┘          │                │
 │     ┌────┴─────┐       └───┬────┘                        │                │
 │     │ docker0 /│           │                             │                │
 │     │ br-xxxx  │           │                             │                │
 │     └────┬─────┘           │                             │                │
 │       NAT (iptables)       │                             │                │
 │          ▼                 ▼                             ▼                │
 │  ┌─────────────────── host network stack / eth0 (parent) ───────────────┐ │
 │  └───────────────────────────────┬──────────────────────────────────────┘ │
 └──────────────────────────────────┼────────────────────────────────────────┘
                                    ▼
                         Physical LAN / Internet

 overlay (multi-host):  ctr ◄──VXLAN (UDP 4789)──► ctr  on a different host
                         control plane: gossip 7946 tcp/udp, swarm 2377 tcp
```

| Driver | Scope | Isolation | Addressable from LAN? | Typical use |
|---|---|---|---|---|
| `bridge` (default) | single host | per-network, NAT to outside | only via published ports | Almost everything on one host |
| `host` | single host | none (shares host stack) | host's own IP and ports | Max network performance, port-heavy tools |
| `none` | single host | total | no | Batch jobs, hardened sandboxes, custom wiring |
| `overlay` | multi-host | per-network, encrypted optionally | via published/ingress ports | Swarm services, attachable cross-host containers |
| `macvlan` | single host | L2 separate from host | yes, own MAC and IP | Legacy apps needing a LAN IP, network appliances |
| `ipvlan` (l2/l3) | single host | shares parent MAC | yes (L2) or routed (L3) | Switches limiting MACs per port, large address counts |

- Docker creates three networks on install: `bridge` (the default bridge, interface `docker0`), `host` and `none`. Others are created by you or by Compose/Swarm.
- A network is **not** the same as a driver: you can create many `bridge` networks, each with its own subnet and Linux bridge device.

## 5. Hands-On

### 5.1 Listing and Inspecting Networks

```bash
docker network ls
docker network inspect bridge --format '{{json .IPAM.Config}}'
```

```text
NETWORK ID     NAME      DRIVER    SCOPE
3f1c0a9d2b7e   bridge    bridge    local
a81b44c5d0e2   host      host      local
c2d9e7f10a33   none      null      local
[{"Subnet":"172.17.0.0/16","Gateway":"172.17.0.1"}]
```

Note the `none` network reports its driver as `null`.

### 5.2 Bridge: The Default Experience

```bash
docker run -d --name web -p 8080:80 nginx:1.27-alpine
docker inspect web --format '{{.NetworkSettings.IPAddress}} {{.HostConfig.NetworkMode}}'
curl -sI http://localhost:8080 | head -1
```

```text
172.17.0.2 default
HTTP/1.1 200 OK
```

The container has a private address on `docker0`; `-p 8080:80` adds a NAT rule so the host port reaches it ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).

### 5.3 Host: Sharing the Host Network Stack

```bash
docker run -d --name web-host --network host nginx:1.27-alpine
curl -sI http://localhost:80 | head -1
docker inspect web-host --format '{{json .NetworkSettings.Ports}}'
```

```text
HTTP/1.1 200 OK
{}
```

Nginx binds directly to the host's port 80. `-p` is ignored (Docker warns) because there is no NAT layer; if port 80 is taken, the container simply fails to start. On Linux this is native. On Docker Desktop, host networking is an opt-in feature in recent releases and "host" means the Desktop VM unless enabled, so `localhost` semantics differ.

### 5.4 None: Loopback Only

```bash
docker run --rm --network none alpine:3.20 ip -br addr
docker run --rm --network none alpine:3.20 wget -T 2 -qO- https://example.com
```

```text
lo               UNKNOWN        127.0.0.1/8
wget: download timed out
```

Useful for processing untrusted files or for containers whose networking you wire up yourself (for example with `nsenter`/`ip link` or a CNI plugin).

### 5.5 Overlay: Multi-Host (Needs Swarm Mode or a KV Setup)

```bash
docker swarm init
docker network create -d overlay --attachable appnet
docker run -d --name o1 --network appnet alpine:3.20 sleep 3600
docker network inspect appnet --format '{{.Driver}} {{.Scope}} {{.Attachable}}'
```

```text
overlay swarm true
```

The overlay driver requires Swarm mode (even a single-node swarm) so that the control plane exists; `--attachable` lets plain `docker run` containers join. Details in [§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md).

### 5.6 Macvlan: A Container With Its Own LAN Identity

```bash
docker network create -d macvlan \
  --subnet 192.168.1.0/24 --gateway 192.168.1.1 \
  --ip-range 192.168.1.192/27 \
  -o parent=eth0 lan
docker run -d --name cam --network lan --ip 192.168.1.200 alpine:3.20 sleep 3600
```

The container appears on the LAN with its own MAC and IP. Two well-known caveats: the **host cannot talk to its own macvlan containers** over the parent interface (the kernel does not hairpin), and the switch or hypervisor must allow multiple MACs on one port (VMware needs promiscuous mode; most cloud VPCs block macvlan entirely). `-d ipvlan -o ipvlan_mode=l2` avoids the MAC proliferation by sharing the parent's MAC.

### 5.7 Attaching to More Than One Network

```bash
docker network create front
docker network create back
docker run -d --name api --network front alpine:3.20 sleep 3600
docker network connect back api
docker inspect api --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}{{"\n"}}{{end}}'
```

```text
front 172.18.0.2
back 172.19.0.2
```

### 5.8 Choosing Quickly: A Decision Sketch

```text
Single host, containers talk to each other + published ports? ──► user-defined bridge
Need the raw host stack (perf, many ports, multicast)?        ──► host
No networking wanted at all?                                  ──► none
Containers across several Docker hosts?                       ──► overlay (or Kubernetes CNI)
Container must have a real LAN IP / L2 presence?              ──► macvlan or ipvlan
```

## 6. Production Usage Notes

- **Default to user-defined bridge networks** per application (Compose does this automatically). Reserve the default `bridge` for throwaway tests ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)).
- **Host networking** appears in monitoring agents (node exporters), ingress proxies needing the client's real source address, and workloads with thousands of ports (RTP/VoIP). It removes per-container NAT cost, which matters at very high packet rates.
- **Overlay** is built into Swarm; outside Swarm most teams use Kubernetes with a CNI plugin (Calico, Cilium, Flannel) rather than standalone Docker overlays.
- **Macvlan/ipvlan** fits migrating legacy services that hard-code a LAN address; it is rarely available in public cloud because of MAC filtering.
- **Address planning:** the default pools (`172.17.0.0/16`, then `172.18.0.0/16` onwards, then `192.168.x.0/20` blocks) can collide with corporate VPNs; set `default-address-pools` in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)) before you run into overlapping routes.
- **Rootless Docker** uses a userspace network stack (slirp4netns or pasta/RootlessKit), so `host` and `macvlan` behave differently and throughput is lower ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)).
- Docker 28 tightened bridge networks so that unpublished container ports are not reachable from other machines on the same L2 segment by targeting the container IP directly; older hosts relied on that gap by accident.

## 7. Security Considerations

- **`--network host` removes the network namespace boundary.** The container can bind any host port, see host interfaces, reach services bound to `127.0.0.1` on the host (including the Docker API on a TCP socket if exposed) and sniff traffic with `CAP_NET_RAW`. Treat it like running the process on the host for networking purposes.
- **Network = trust zone.** Containers on the same bridge can reach each other on all ports by default; put databases on a network the internet-facing tier cannot join ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- **`--internal` networks** have no route out, a cheap egress control for backends.
- **Macvlan containers bypass the host firewall rules** that normally filter published-port traffic (Docker's iptables chains are not in the path); enforce policy at the switch or inside the container.
- **Overlay data-plane encryption** is off by default; enable `-o encrypted` (IPsec ESP) on untrusted links, and keep ports 2377, 7946 and 4789 off the public internet.
- **`none` plus no capabilities** is the right shape for parsing untrusted input.
- Published ports bind to `0.0.0.0` by default and, because Docker writes its own firewall rules, can bypass `ufw`/`firewalld` host rules. Bind to `127.0.0.1` when only local access is intended ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Containers cannot reach each other by name | On the default `bridge`, which has no embedded DNS | Use a user-defined bridge or Compose network ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)) |
| `-p` ignored, WARNING: published ports are discarded | Container uses `--network host` | Remove `-p`; the app binds host ports itself |
| Host cannot ping its macvlan container | Kernel limitation on the parent interface | Create a macvlan sub-interface on the host with its own route, or use ipvlan L3 |
| Macvlan container unreachable from the LAN | Switch port security / hypervisor blocks extra MACs | Enable promiscuous mode, or use ipvlan |
| `network ... is not attachable` or overlay create fails | Swarm not initialized or network not `--attachable` | `docker swarm init`; create with `--attachable` |
| Pool overlap: `Pool overlaps with other one on this address space` | Requested subnet collides with an existing network or host route | Pick another subnet or change `default-address-pools` |
| VPN stops working after a `docker network create` | Auto-assigned subnet overlaps the VPN's range | Pin subnets explicitly |
| `address already in use` with host networking | Host port taken | Free the port or move to bridge with `-p` |

## 9. Best Practices

- One user-defined bridge per application or tier; name them meaningfully.
- Define explicit subnets in shared environments to avoid overlap.
- Prefer publishing only what is needed, bound to a specific host address.
- Use `host` only when you can state the measured or functional reason.
- Use `--internal` for backend networks that must never reach the internet.
- Document the driver and subnet choices alongside the Compose file.
- On Windows/macOS, remember containers run inside a VM; "host" and `localhost` refer to that VM unless the Desktop feature says otherwise.

## 10. Common Anti-Patterns / Mistakes

- Running every container on the default bridge and wiring them with `--link` or hard-coded IPs.
- Reaching for `--network host` to "fix" a connectivity problem instead of diagnosing it.
- Using macvlan in a cloud VM and wondering why nothing arrives.
- Using an overlay network on a single host when a bridge would do.
- Publishing database ports (`-p 5432:5432`) to all interfaces.
- Assuming network names are global: networks exist per daemon, and Compose prefixes them with the project name.
- Hard-coding container IPs, which change on recreate.

## 11. Interview Questions

**🎯 Beginner:** _"Name Docker's built-in network drivers and say what each is for."_
**Model answer:** `bridge` is the default: a private virtual switch on one host, with NAT to the outside and published ports for inbound traffic. `host` removes network isolation so the container shares the host's stack. `none` gives only a loopback interface. `overlay` connects containers across multiple Docker hosts using VXLAN, mostly with Swarm. `macvlan` (and `ipvlan`) gives containers addresses directly on the physical network. Docker creates `bridge`, `host` and `none` at install time.
_What the interviewer is probing for:_ Accurate one-line positioning of each driver, plus awareness that the default driver is bridge.

**🎯 Intermediate:** _"A service on `--network host` works, but the same service on a bridge with `-p 3000:3000` does not. What would you check?"_
**Model answer:** Under host networking the app binds the host's interfaces, so listening on `127.0.0.1` works for local clients. On a bridge the app must listen on `0.0.0.0` inside the container, because the traffic arrives on the container's `eth0`, not its loopback. I would check `ss -ltnp` inside the container for the bind address, confirm the mapping with `docker port`, inspect the NAT rule with `iptables -t nat -S DOCKER`, and test from another container on the same network to separate app problems from publishing problems.
_What the interviewer is probing for:_ Understanding of the bind-address pitfall and of NAT versus shared stack.

**🎯 Senior:** _"Security wants a three-tier app (proxy, API, database) where the database has no internet access and is unreachable from the proxy. Design the networks."_
**Model answer:** Create `edge` (proxy and API) and `data` (API and database) as separate user-defined bridges, with `data` marked `--internal` so it has no egress. The API joins both networks; the proxy joins only `edge`; the database only `data`. Only the proxy publishes ports, bound to the required host address. Because networks are isolated L2/L3 domains, the proxy has no route to the database. Add resource and capability limits as defence in depth, and verify with `docker exec proxy nc -zv db 5432` failing. In Compose this is two `networks:` entries with `internal: true` on `data`.
_What the interviewer is probing for:_ Using multiple networks as segmentation and `--internal` for egress control.

**🎯 Architect:** _"A vendor appliance container must appear on the corporate VLAN with a fixed IP, in an on-prem cluster and later in AWS. What are the options and risks?"_
**Model answer:** On-prem, macvlan or ipvlan on a VLAN sub-interface (`parent=eth0.100`) gives the container a LAN identity; ipvlan L2 is safer if the switch limits MACs per port. Risks: the host cannot reach the container directly, no Docker firewall filtering, and IP management must be coordinated with the network team (use `--ip-range` plus a reserved block). In AWS, macvlan is blocked by the VPC (MAC and source/dest checks), so use the VPC's own addressing: ENI-per-pod/task models (ECS awsvpc, EKS VPC CNI) or secondary ENI IPs with ipvlan, or front the appliance with a load balancer and static target. I would abstract the addressing behind configuration, and accept that parity between environments is by contract (a reachable IP) rather than by driver.
_What the interviewer is probing for:_ Knowing macvlan's physical-network assumptions and cloud limits, and designing for portability.

## 12. Common Misconceptions

- "Docker has one network." Every daemon has several, and containers can join multiple.
- "`host` is just a faster bridge." It removes isolation entirely.
- "Overlay works out of the box on any host pair." It needs Swarm (or an external store in legacy setups) and open control and VXLAN ports.
- "`none` means the container is isolated from the host kernel." It only removes the network interfaces.
- "Macvlan containers can talk to the host." Not over the parent interface by default.
- "`-p` works with every driver." It has no effect with `host` and is unnecessary with macvlan.

## 13. 🔑 Key Takeaways

- A driver defines the wiring; a network is one instance of a driver; a container can attach to many.
- `bridge` is the default and right for single-host apps; use user-defined bridges, not `docker0`.
- `host` trades isolation for performance and simplicity; `none` gives loopback only.
- `overlay` spans hosts through VXLAN and needs Swarm's control plane; `macvlan`/`ipvlan` put containers on the physical LAN.
- Plan subnets (`default-address-pools`) before they collide with VPNs.
- Network segmentation is a primary security tool: separate networks, `--internal`, minimal published ports.

## 14. Related Concepts & What's Next

Related: namespaces and veth pairs ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), Compose networks ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), port publishing ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), overlay internals ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), troubleshooting tools ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), segmentation patterns ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)). Next, [§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md) dissects the `bridge` driver and why user-defined bridges differ from the default one.

**Next Section:** [§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md) — `Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md`
