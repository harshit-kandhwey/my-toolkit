# Section 43 (Part 6): The Default Bridge Network and Custom Bridge Networks

## 1. Definition

**Plain language:** The *default bridge* is the network every container joins if you do not say otherwise. It works, but it is a legacy design with weak isolation and no name-based discovery. A *user-defined (custom) bridge* is a bridge network you create yourself; it adds automatic DNS between containers, better isolation, live attach/detach, and per-network settings.

**Precise definition:** Both are instances of the `bridge` driver, each backed by a Linux bridge device on the host (a virtual L2 switch). The default network is named `bridge` and uses the device `docker0`, subnet `172.17.0.0/16` unless reconfigured. User-defined bridges get a device named `br-<first 12 chars of network ID>` (or a name you choose with `com.docker.network.bridge.name`) and a subnet from `default-address-pools`. Each container endpoint is one end of a veth pair whose other end is enslaved to the bridge. Outbound traffic is masqueraded (SNAT) by iptables/nftables; inbound traffic exists only for published ports ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).

> 💡 **Tip:** On the default bridge, containers talk by IP address only. On a user-defined bridge, they talk by container name, service name or network alias, resolved by Docker's embedded DNS at `127.0.0.11` ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)).

## 2. Why This Matters

- The single most common beginner failure: two containers on the default bridge cannot reach each other by name.
- Compose creates a user-defined bridge per project; understanding it explains why `db:5432` "just works" ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)).
- Hard-coded IPs and `--link` are fragile and deprecated; the custom bridge is the supported replacement.
- Isolation: anything on `docker0` can reach everything else on `docker0`. Separate custom bridges give you cheap network segmentation ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- Subnet and MTU choices made here decide whether your VPN, corporate routes and overlay-over-VPN tunnels keep working.

## 3. Prerequisites and Dependencies

Requires the driver overview ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), network namespaces and veth pairs ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)), and `docker run` basics ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)). Daemon-wide bridge settings (`bip`, `default-address-pools`) live in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). DNS behaviour is expanded in [§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md); packet handling in [§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md).

## 4. Architecture / Conceptual Diagram

```text
                               DOCKER HOST
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  Default bridge "bridge"             User-defined bridge "appnet"        │
 │  device docker0  172.17.0.1/16       device br-9f3a1c2b7d10 172.20.0.1/16│
 │                                                                          │
 │  ┌────────┐   ┌────────┐             ┌────────┐   ┌────────┐            │
 │  │ c1     │   │ c2     │             │ api    │   │ db     │            │
 │  │.17.0.2 │   │.17.0.3 │             │.20.0.2 │   │.20.0.3 │            │
 │  └──┬─────┘   └──┬─────┘             └──┬─────┘   └──┬─────┘            │
 │   vethA        vethB                  vethC        vethD                 │
 │     └─────┬──────┘                      └─────┬──────┘                   │
 │       ┌───┴────┐                          ┌───┴────┐                     │
 │       │docker0 │                          │br-9f3a │                     │
 │       └───┬────┘                          └───┬────┘                     │
 │           │   no DNS by name                  │  embedded DNS 127.0.0.11 │
 │           │   (IP only)                       │  api ◄──► db by name     │
 │   ────────┴────── routing + iptables (MASQUERADE, DOCKER-USER, ──────────│
 │                    DOCKER-ISOLATION: docker0 ◄✕► br-9f3a)                │
 │                              ▼                                           │
 │                        host eth0 ──► LAN / Internet                      │
 └──────────────────────────────────────────────────────────────────────────┘
```

| Property | Default bridge (`docker0`) | User-defined bridge |
|---|---|---|
| Name/alias DNS between containers | No (IP only; legacy `--link`) | Yes, embedded DNS |
| Isolation from other networks | All containers share it | Per-network; networks isolated from each other by default |
| Attach/detach running container | Must stop and recreate | `docker network connect/disconnect` live |
| Configure per network | Only daemon-wide (`daemon.json`) | Subnet, gateway, MTU, ICC, masquerade, bridge name per network |
| Environment variable sharing | `--link` only | Not used; use DNS and shared config |
| Default for `docker run` | Yes | Only with `--network` or Compose |
| Removable | No | Yes (`docker network rm`) |

- **Inter-container communication (ICC):** on by default on both; it can be disabled per network with `com.docker.network.bridge.enable_icc=false`, after which containers talk only through published ports or explicit links.
- **Network isolation rules:** Docker installs rules so traffic is not forwarded between two different bridge networks, which is why two user-defined networks are separate security zones.

## 5. Hands-On

### 5.1 Proving the DNS Difference

```bash
docker run -d --name d1 alpine:3.20 sleep 3600
docker run --rm alpine:3.20 ping -c1 -W2 d1

docker network create appnet
docker run -d --name u1 --network appnet alpine:3.20 sleep 3600
docker run --rm --network appnet alpine:3.20 ping -c1 u1
```

```text
ping: bad address 'd1'
PING u1 (172.20.0.2): 56 data bytes
64 bytes from 172.20.0.2: seq=0 ttl=64 time=0.085 ms
```

Same driver, different behaviour: only the custom bridge resolves names.

### 5.2 Creating a Custom Bridge With Explicit Settings

```bash
docker network create \
  --driver bridge \
  --subnet 10.50.0.0/24 \
  --gateway 10.50.0.1 \
  --ip-range 10.50.0.128/25 \
  -o com.docker.network.bridge.name=br-app \
  -o com.docker.network.driver.mtu=1450 \
  --label env=dev \
  appnet2
ip -br addr show br-app
docker network inspect appnet2 --format '{{json .IPAM.Config}} {{json .Options}}'
```

```text
br-app           UP             10.50.0.1/24
[{"Subnet":"10.50.0.0/24","IPRange":"10.50.0.128/25","Gateway":"10.50.0.1"}] {"com.docker.network.bridge.name":"br-app","com.docker.network.driver.mtu":"1450"}
```

`--ip-range` limits what Docker auto-assigns, leaving the lower half for static addresses. Use a lower MTU when running over VPN or VXLAN tunnels with reduced path MTU.

### 5.3 Static IPs and Aliases

```bash
docker run -d --name db --network appnet2 --ip 10.50.0.10 \
  --network-alias database --network-alias pg postgres:16-alpine
docker run --rm --network appnet2 alpine:3.20 getent hosts database pg db
```

```text
10.50.0.10        database  database
10.50.0.10        pg        pg
10.50.0.10        db        db
```

`--ip` is only valid on user-defined networks that have an explicit `--subnet`. Aliases are scoped to the network they are declared on and may be shared by several containers (DNS round-robin).

### 5.4 Connecting and Disconnecting Live

```bash
docker network create backend
docker network connect backend u1
docker inspect u1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}  {{end}}'
docker network disconnect backend u1
docker inspect u1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{$v.IPAddress}}  {{end}}'
```

```text
appnet 172.20.0.2  backend 172.21.0.2
appnet 172.20.0.2
```

To change an alias or IP on an existing attachment, disconnect and connect again with `--alias`/`--ip`. A container on the default bridge can also be connected to other networks, but you cannot change its default-bridge settings without recreating it.

### 5.5 Isolating With an Internal Network

```bash
docker network create --internal secure
docker run --rm --network secure alpine:3.20 wget -T2 -qO- https://example.com
docker run -d --name vault --network secure alpine:3.20 sleep 3600
docker run --rm --network secure alpine:3.20 ping -c1 vault
```

```text
wget: download timed out
PING vault (172.22.0.2): 56 data bytes
...
```

`--internal` omits the masquerade rule and the default route out; containers still resolve and reach each other.

### 5.6 Disabling Inter-Container Communication

```bash
docker network create -o com.docker.network.bridge.enable_icc=false locked
docker run -d --name l1 --network locked alpine:3.20 sleep 3600
docker run --rm --network locked alpine:3.20 ping -c1 -W2 l1
```

```text
PING l1 (172.23.0.2): 56 data bytes
--- l1 ping statistics ---
1 packets transmitted, 0 packets received, 100% packet loss
```

With ICC off, bridge forwarding between containers on that network is dropped. Outbound internet access still works.

### 5.7 Reconfiguring the Default Bridge in daemon.json

```json
{
  "bip": "10.200.0.1/24",
  "default-address-pools": [
    { "base": "10.201.0.0/16", "size": 24 }
  ],
  "mtu": 1450
}
```

```bash
sudo systemctl restart docker
docker network inspect bridge --format '{{json .IPAM.Config}}'
```

```text
[{"Subnet":"10.200.0.0/24","Gateway":"10.200.0.1"}]
```

`bip` sets the `docker0` address and subnet; `default-address-pools` governs where user-defined networks come from (each new network gets a `/24` slice of `10.201.0.0/16` here). Restarting the daemon stops non-`live-restore` containers, so plan the maintenance window ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

### 5.8 Looking at the Plumbing

```bash
ip -br link show type bridge
bridge link show
docker network inspect appnet --format '{{.Id}}' | cut -c1-12
sudo iptables -t nat -S POSTROUTING | grep MASQ
```

```text
docker0          UP
br-9f3a1c2b7d10  UP
veth1a2b3c4@if7  master br-9f3a1c2b7d10
9f3a1c2b7d10
-A POSTROUTING -s 172.20.0.0/16 ! -o br-9f3a1c2b7d10 -j MASQUERADE
```

The device name derives from the network ID, which is how you map a `br-xxxx` interface in `ip a` back to a Docker network.

### 5.9 Compose Equivalent

```yaml
services:
  api:
    image: myorg/api:1.4
    networks: [front, back]
  db:
    image: postgres:16-alpine
    networks: [back]
networks:
  front: {}
  back:
    internal: true
    ipam:
      config:
        - subnet: 10.60.0.0/24
```

Even without a `networks:` key Compose creates `<project>_default`, a user-defined bridge, which is why service names resolve.

## 6. Production Usage Notes

- **Never rely on the default bridge** for application traffic; create a network per application or per tier (Compose does this for you).
- **Pin subnets** in shared or VPN-connected environments. Auto-allocation walks `172.17-31.0.0/16`, then `192.168.0.0/16` in `/20` chunks; machines with many networks can run out or collide with corporate ranges.
- **Number of networks:** each bridge consumes a subnet and a device. Hundreds of Compose projects on one host can exhaust the default pool; widen `default-address-pools` with smaller `size` (for example `/24`).
- **MTU:** set the network MTU to the smallest path MTU (VPNs, cloud overlay, WireGuard). Symptoms of mismatch are hangs on large transfers while ping works.
- **Stable addressing:** use aliases and service names, not IPs. If you must pin, use `--ip` with a reserved `--ip-range` split.
- **Cleaning up:** unused networks are removed by `docker network prune`; they are cheap but leave stale `br-` devices only until pruned ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).
- **IPv6:** enable per network with `--ipv6` (and a subnet) or daemon-wide `"ipv6": true` with `fixed-cidr-v6`; recent Engine releases make IPv6 on user-defined bridges simpler, but verify firewall behaviour separately.
- **Docker Desktop:** the bridge lives in the Desktop VM; `docker0` is not visible in the host's `ip addr`, and container IPs are not routable from the host.

## 7. Security Considerations

- **Default bridge = flat network.** Any container (including a compromised one) can reach every other container on `docker0` by IP, and with `CAP_NET_RAW` (granted by default) can attempt ARP spoofing against neighbours. Mitigate with per-tier custom bridges, `--cap-drop NET_RAW` ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)) and `enable_icc=false` where containers need only the outside world.
- **Network segmentation is the unit of trust:** place a service on only the networks it needs; a container attached to both `front` and `back` is a bridge between zones, so treat it as a security-critical component.
- **`--internal`** blocks egress, defeating many data-exfiltration and reverse-shell paths.
- **Published ports bypass host firewalls** like `ufw` because Docker inserts its own rules. Use the `DOCKER-USER` chain for policy, or bind to loopback ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).
- **Do not expose the Docker TCP API** on a bridge-reachable address without TLS; containers on that network could take over the host ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **`--link` leaks environment variables** (including secrets) into linked containers; another reason to avoid it.
- **Promiscuous bridge sniffing:** anything with host-level access to `br-*` can capture all container traffic; restrict host access and consider application-layer TLS.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `ping: bad address 'svc'` | Default bridge has no name resolution | Move both containers to a user-defined network |
| `Invalid address ... --ip` / "user specified IP address is supported on user defined networks only" | `--ip` on the default bridge or network lacks `--subnet` | Create a custom network with `--subnet` |
| `Pool overlaps with other one on this address space` | Subnet clashes with another Docker network or interface | Choose a free subnet or edit `default-address-pools` |
| `all predefined address pools have been fully subnetted` | Pool exhausted | Add pools with `/24` size or prune unused networks |
| Containers lose internet after enabling a VPN | VPN claims a range Docker also uses; routes conflict | Re-create networks on non-overlapping subnets |
| Large downloads hang, small pings succeed | MTU mismatch | Set `com.docker.network.driver.mtu` / daemon `mtu` |
| `network has active endpoints` on `network rm` | Containers still attached (even stopped) | `docker rm` them or `docker network disconnect` first |
| DNS works for names, not for external hosts | Embedded DNS forwarding to a broken host resolver | Set `dns` in `daemon.json` or `--dns` ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)) |
| Cannot reach container IP from the host (Desktop) | Bridge is inside a VM | Publish a port instead |

## 9. Best Practices

- Create user-defined bridges for every multi-container application; let Compose do it where possible.
- Reference peers by service name or alias, never by IP.
- Specify subnets explicitly where overlap is possible; document them.
- Keep `docker0` for ad-hoc one-offs; set `bip` so it avoids your corporate ranges.
- Split frontend and backend networks and mark data networks `internal`.
- Drop `NET_RAW` and disable ICC where full mesh connectivity is unnecessary.
- Set MTU deliberately when tunnels are involved.
- Remove unused networks routinely with `docker network prune` in non-production environments.

## 10. Common Anti-Patterns / Mistakes

- Using `--link` for new deployments (deprecated, brittle).
- Hard-coding container IPs obtained from `docker inspect`.
- Putting every service on one network "for simplicity".
- Publishing ports to reach another container (use the shared network and the container port instead).
- Using `localhost` inside a container to reach a sibling; `localhost` is the container itself.
- Editing `iptables` rules by hand rather than using `DOCKER-USER`.
- Creating networks with default pools on a laptop connected to several VPNs.

## 11. Interview Questions

**🎯 Beginner:** _"Two containers run on the same host with plain `docker run`. One cannot ping the other by name. Why, and what is the quickest fix?"_
**Model answer:** Both landed on the default `bridge` network, which does not provide DNS resolution of container names; it only supports IP addressing and the legacy `--link`. The fix is to create a user-defined bridge with `docker network create appnet` and start both with `--network appnet`, or connect them live with `docker network connect appnet <name>`. On a custom bridge, Docker's embedded DNS at 127.0.0.11 resolves container names and network aliases. Compose does this automatically per project.
_What the interviewer is probing for:_ The default versus user-defined bridge difference, and that name resolution is a custom-network feature.

**🎯 Intermediate:** _"List at least five concrete advantages of user-defined bridges over the default bridge."_
**Model answer:** Automatic DNS between containers; better isolation, since only containers attached to the network can talk on it and other networks are firewalled off; containers can be attached and detached while running; per-network configuration such as subnet, gateway, `--ip-range`, MTU, ICC and masquerade, instead of only daemon-wide settings; no need for `--link` and its environment-variable sharing; ability to give network aliases and static IPs; and they can be marked `--internal` or removed independently. The default bridge exists mainly for backward compatibility.
_What the interviewer is probing for:_ Depth beyond "DNS", including operational and security differences.

**🎯 Senior:** _"After a corporate VPN rollout, developers' containers cannot reach internal services, yet it worked yesterday. How do you diagnose and permanently fix it?"_
**Model answer:** Suspect subnet overlap: Docker auto-allocated `172.x` or `192.168.x` ranges that now overlap the VPN's routes, so packets for corporate hosts are routed to a local bridge instead of the tunnel. Confirm with `ip route`, `docker network inspect` for subnets, and `traceroute` from a container. Short term, recreate affected networks on non-overlapping subnets. Permanent fix: set `bip` and `default-address-pools` in `daemon.json` to a range reserved for Docker (for example `10.201.0.0/16` sliced into `/24`s), roll it out through configuration management, and pin explicit subnets in Compose for shared stacks. Also check MTU if only large transfers fail, since VPN encapsulation reduces it.
_What the interviewer is probing for:_ Systematic diagnosis (routes, subnets) and a fleet-level preventive configuration.

**🎯 Architect:** _"Design network policy for a multi-tenant CI host that runs untrusted build containers next to a shared cache service."_
**Model answer:** Give each job its own user-defined bridge (created and removed by the runner) so tenants cannot see each other; attach the cache service to a dedicated network that only the intended job networks join through a proxy, or expose the cache on a published port protected by authentication and TLS. Disable ICC where a job has a single container, drop `NET_RAW`, set per-network MTU and fixed pools sized for many short-lived networks (`/28` or `/29` slices of a reserved block) so the pool is not exhausted, and add egress policy in `DOCKER-USER` (or `--internal` plus an explicit egress proxy). Monitor for leaked networks via a reaper job. Acknowledge the limits: containers still share a kernel, so for truly hostile code add gVisor/Kata or VM-level isolation.
_What the interviewer is probing for:_ Applying per-network isolation at scale, address-pool planning, and awareness of where network controls stop.

## 12. Common Misconceptions

- "The default bridge and custom bridges are different drivers." Same driver, different features and defaults.
- "Containers on different custom bridges can talk through the host IP by default." They are isolated unless you publish ports or attach to a common network.
- "`localhost` reaches sibling containers." It reaches the container itself.
- "`--link` is the way to connect containers." Deprecated; use networks.
- "You must publish ports for containers to talk to each other." Container-to-container traffic on a shared network uses container ports directly.
- "Deleting a container frees its IP permanently." Addresses are reassigned; never rely on them.

## 13. 🔑 Key Takeaways

- Default bridge (`docker0`): IP-only, flat, legacy. User-defined bridge: DNS, isolation, live connect, per-network options.
- Compose creates a user-defined bridge per project automatically.
- Control addressing with `--subnet`, `--gateway`, `--ip-range`, `--ip`, and daemon `bip` / `default-address-pools`.
- Use `--internal` for no-egress networks and `enable_icc=false` to stop east-west traffic.
- Match MTU to the real path and avoid subnet overlap with VPNs.
- Segment by network: attach each container only to the networks it needs.

## 14. Related Concepts & What's Next

Related: driver overview ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), Compose networks ([§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), daemon configuration ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), port publishing ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), troubleshooting ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), segmentation ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)). Next, [§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md) explains how the embedded DNS server resolves names, aliases and external hosts.

**Next Section:** [§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md) — `Section-44-Part6-Container-DNS-and-Service-Discovery.md`
