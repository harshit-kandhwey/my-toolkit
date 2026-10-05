# Section 46 (Part 6): Overlay Networks and Multi-Host Networking Concepts

## 1. Definition

**Plain language:** A bridge network connects containers on one host. An overlay network makes containers on *different* hosts behave as if they were plugged into the same virtual switch, by wrapping their Ethernet frames inside ordinary UDP packets that travel over the hosts' real network.

**Precise definition:** The Docker `overlay` driver builds a distributed virtual network on top of an existing IP underlay using **VXLAN** (RFC 7348): each container frame is encapsulated in a UDP datagram (destination port **4789**) addressed to the remote host's IP, identified by a 24-bit **VNI** (VXLAN Network Identifier). Overlay networks require a cluster-wide state store; in modern Docker that is the **Swarm** Raft-backed control plane (the standalone external key-value store mode was removed long ago). Other multi-host options are `macvlan`/`ipvlan` (containers appear directly on the physical network) and, outside Docker, CNI plugins under Kubernetes ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)).

> 💡 **Tip:** "Overlay" describes the *data plane* trick (encapsulation). The *control plane* (who owns which IP, which VTEP hosts a container) is gossiped between daemons and is what makes the network feel seamless.

## 2. Why This Matters

- A single host is a single point of failure and a capacity ceiling; any real deployment eventually needs containers on several machines that still reach each other by name.
- Overlay networking is the reason Swarm services can scale across nodes without port juggling, and the same encapsulation ideas appear in Kubernetes CNIs (Flannel VXLAN, Calico VXLAN mode, Cilium).
- Overlay misconfiguration is a classic source of "works on one node, fails across nodes" outages: blocked UDP 4789, MTU mismatches, and overlapping subnets.
- Interviewers use overlay questions to separate people who memorized `docker network create -d overlay` from those who understand the packet path.

## 3. Prerequisites and Dependencies

Requires the network driver landscape ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), bridge networking and the `veth` pair model ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), embedded DNS ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), and NAT and published ports ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)). Network namespaces are the building block for everything below ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)). Overlay networks need Swarm mode initialized ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)), and the daemon is configured per [§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md).

## 4. Architecture / Conceptual Diagram

```text
        Host A (192.168.1.10)                       Host B (192.168.1.11)
  ┌──────────────────────────────┐            ┌──────────────────────────────┐
  │ container web   10.0.1.3     │            │ container api   10.0.1.5     │
  │      eth0 ──veth──┐          │            │      eth0 ──veth──┐          │
  │   ┌───────────────▼───────┐  │            │   ┌───────────────▼───────┐  │
  │   │ overlay netns         │  │            │   │ overlay netns         │  │
  │   │  br0 (L2 bridge)      │  │            │   │  br0 (L2 bridge)      │  │
  │   │  vxlan0 (VTEP, VNI N) │  │            │   │  vxlan0 (VTEP, VNI N) │  │
  │   └───────────┬───────────┘  │            │   └───────────┬───────────┘  │
  │        host IP stack         │            │        host IP stack         │
  │   eth0 192.168.1.10          │            │   eth0 192.168.1.11          │
  └──────────────┬───────────────┘            └──────────────┬───────────────┘
                 │   underlay: any routed IP network         │
                 └──────────►  UDP 4789 (VXLAN)  ◄───────────┘

  Packet web ──► api (10.0.1.5)
  inner:  [Eth][IP 10.0.1.3 ► 10.0.1.5][TCP payload]
  outer:  [Eth][IP 192.168.1.10 ► 192.168.1.11][UDP 4789][VXLAN VNI N][inner frame]

  Control plane (gossip + Raft)       Ports required between all nodes
  ─────────────────────────────       ─────────────────────────────────
  TCP 2377  manager Raft/cluster      TCP 2377   (managers only)
  TCP/UDP 7946  node gossip (serf)    TCP+UDP 7946
  UDP 4789  VXLAN data plane          UDP 4789
  ESP (IP proto 50) if --opt encrypted
```

- **VTEP (VXLAN Tunnel Endpoint):** the `vxlan0` device in a per-network namespace on every host.
- **Per-network namespace:** Docker creates a namespace per overlay network on each host (visible under `/var/run/docker/netns`, names like `1-<id>`), containing `br0` and `vxlan0`; container `veth` ends attach to `br0`.
- **Learning without flooding:** daemons gossip container MAC/IP-to-host mappings and program forwarding (FDB) and ARP entries, so there is no broadcast flooding across the underlay.
- **Subnets:** each overlay network gets its own subnet (by default allocated from `10.0.0.0/8` pools in /24 slices) and a gateway; containers also get one interface per network they join.
- **MTU:** VXLAN adds about 50 bytes of overhead, so overlay MTU defaults to 1450 on a 1500-byte underlay.

## 5. Hands-On

### 5.1 Create a Swarm and an Attachable Overlay

```bash
# On the first node
docker swarm init --advertise-addr 192.168.1.10
# On other nodes, run the printed 'docker swarm join --token ...' command

docker network create -d overlay --attachable --subnet 10.20.0.0/24 appnet
docker network ls --filter driver=overlay
```

```text
NETWORK ID     NAME              DRIVER    SCOPE
k3p8w1zq7u2a   appnet            overlay   swarm
x91b7c8d2m4n   ingress           overlay   swarm
```

`--attachable` lets plain `docker run` containers join; without it only Swarm services can. Scope `swarm` (not `local`) marks a cluster-wide network.

### 5.2 Cross-Host Name Resolution and Reachability

```bash
# Host A
docker run -d --name web --network appnet nginx:1.27-alpine
# Host B
docker run --rm -it --network appnet alpine:3.20 sh -c "wget -qO- http://web | head -n 3"
```

```text
<!DOCTYPE html>
<html>
<head>
```

The container on Host B resolved `web` via the embedded DNS server ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)) and reached it across the VXLAN tunnel. The overlay network appears on Host B only once a container there joins it (networks are created lazily per node).

### 5.3 Inspect the Overlay

```bash
docker network inspect appnet --format '{{json .IPAM.Config}} {{json .Options}}'
docker network inspect appnet --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'
```

```text
[{"Subnet":"10.20.0.0/24","Gateway":"10.20.0.1"}] null
web 10.20.0.3/24
```

### 5.4 Look Inside the Overlay Namespace (Linux host)

```bash
sudo ls /var/run/docker/netns
sudo nsenter --net=/var/run/docker/netns/1-k3p8w1zq7u ip -d link show vxlan0
sudo nsenter --net=/var/run/docker/netns/1-k3p8w1zq7u bridge fdb show dev vxlan0
```

```text
vxlan id 4097 srcport 0 0 dstport 4789 proxy l2miss l3miss ...
02:42:0a:14:00:04 dst 192.168.1.11 self permanent
```

The FDB entry maps a remote container MAC to the remote host IP: the control plane doing its job. `l2miss`/`l3miss` make the kernel ask userspace (the daemon) on a miss.

### 5.5 Encrypted Overlay

```bash
docker network create -d overlay --opt encrypted --attachable securenet
```

This programs IPsec ESP (AES-GCM) between nodes for that network's VXLAN traffic. Allow IP protocol 50 between hosts, not only UDP 4789.

### 5.6 Services, the VIP and the Ingress Routing Mesh

```bash
docker service create --name web --replicas 3 --network appnet -p 8080:80 nginx:1.27-alpine
docker service inspect web --format '{{json .Endpoint.VirtualIPs}}'
docker run --rm --network appnet alpine:3.20 nslookup web
docker run --rm --network appnet alpine:3.20 nslookup tasks.web
```

```text
[{"NetworkID":"k3p8...","Addr":"10.20.0.2/24"},{"NetworkID":"x91b...","Addr":"10.0.0.8/24"}]
Name: web        Address: 10.20.0.2
Name: tasks.web  Address: 10.20.0.3 / 10.20.0.4 / 10.20.0.5
```

The service name resolves to a single **VIP**; the kernel's IPVS (via an `iptables` mangle mark) load-balances to the task IPs. `tasks.<service>` returns the individual task IPs. With `--endpoint-mode dnsrr` the name resolves straight to the task IPs (round-robin DNS, no VIP). Published ports (`-p 8080:80`) in default **ingress mode** are reachable on port 8080 of *every* node, even nodes running no replica, because traffic enters the special `ingress` overlay, hits `ingress_sbox`, and is IPVS-balanced to a task. `mode=host` publishing bypasses the mesh.

### 5.7 Macvlan as the Non-Overlay Alternative

```bash
docker network create -d macvlan --subnet 192.168.1.0/24 --gateway 192.168.1.1 \
  -o parent=eth0 lan
docker run --rm -d --network lan --ip 192.168.1.200 nginx:1.27-alpine
```

Containers get real addresses on the physical LAN with no encapsulation, but the host cannot reach its own macvlan containers directly, many switches limit MAC counts, and promiscuous mode is needed on some virtual NICs.

## 6. Production Usage Notes

- **Firewalls and cloud security groups** must allow TCP 2377 (managers), TCP+UDP 7946 and UDP 4789 between all nodes; this is the single most common failure.
- **MTU:** if the underlay is already tunneled (cloud VPN, WireGuard, GRE) set a lower MTU: `docker network create -d overlay -o com.docker.network.driver.mtu=1400 ...`. Symptoms of a mismatch are small packets working and large transfers hanging.
- **Subnet planning:** pick explicit `--subnet` values that do not overlap host networks, VPN ranges, or other overlays; overlapping ranges cause silent misrouting. Configure `default-address-pools` in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).
- **Performance:** VXLAN costs CPU and 5 to 10 percent throughput without NIC offload; prefer NICs with UDP-tunnel segmentation offload, or use `host` publishing and macvlan for latency-critical paths.
- **Ingress mesh trade-off:** the mesh hides client source IPs (SNAT) unless you use `mode=host`; put a real load balancer in front for TLS and source-IP-aware logic ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).
- **Scale limits:** gossip scales to hundreds of nodes; very large overlays or many networks add control-plane chatter. Beyond that, Kubernetes with a CNI is the usual path ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).
- **Stateful dependence:** overlay state lives in Swarm; losing manager quorum freezes network changes while existing traffic keeps flowing.

## 7. Security Considerations

- **Unencrypted by default:** VXLAN traffic is cleartext and unauthenticated on the wire. Anyone on the underlay can sniff it, and anyone who can send UDP 4789 to a node can inject frames into an overlay. Use `--opt encrypted` or isolate the underlay with a private VLAN and strict security groups.
- **Never expose 2377, 7946, 4789 to the internet.** Restrict them to node-to-node source ranges.
- **Encrypted-overlay caveat:** encryption applies to container-to-container traffic on that network; traffic on the `ingress` network is not encrypted by `--opt encrypted` on a user network, and encrypted overlays cost throughput.
- **Segmentation:** put tiers on separate overlays (frontend, backend, data) so a compromised web container cannot reach the database network ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)). Use `--internal` for networks with no outbound route.
- **Attachable overlays** let any user with Docker access on a node join the network and talk to services; treat the flag as a trust grant.
- **Swarm join tokens** are credentials: rotate with `docker swarm join-token --rotate`, and enable autolock to protect manager keys.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Containers on different nodes cannot ping or resolve each other | UDP 4789 or 7946 blocked | Open ports node-to-node; test with `nc -zvu <ip> 4789` and a `tcpdump` on both sides |
| Small requests work, large downloads stall | MTU mismatch from nested tunnels | Lower the network MTU option; verify with `ping -M do -s 1400` |
| `network ... not found` when running a container | Network is not `--attachable`, or node is not in the swarm | Recreate with `--attachable`; check `docker info` for `Swarm: active` |
| Intermittent timeouts after idle periods | Cloud NAT or firewall dropping idle UDP conntrack, stale FDB entries | Raise conntrack timeouts, restart the container or the daemon on the affected node |
| Service VIP unreachable but task IPs work | IPVS/iptables rules missing or conntrack stale | Check `iptables -t mangle -S`, `ipvsadm -Ln` inside the network namespace; update the service to reschedule tasks |
| Address overlap, odd routes | Overlay subnet collides with host or VPN range | Recreate network with explicit `--subnet`; set `default-address-pools` |
| Encrypted network drops all traffic | ESP (protocol 50) blocked | Allow IP protocol 50, or fall back to a private underlay |
| Published port unreachable on a node | Ingress mesh disabled by `mode=host`, or host firewall blocks the port | Confirm publish mode with `docker service inspect`; check host firewall |

## 9. Best Practices

- Allocate subnets deliberately and document them; never rely on default pools in a multi-environment estate.
- One overlay per trust boundary; keep databases on `--internal` overlays.
- Encrypt overlays that cross untrusted links, and measure the throughput cost before committing.
- Validate MTU end to end (`ping -M do`) as part of node onboarding.
- Open exactly the three Swarm ports, node-to-node only, in firewalls and security groups.
- Use `dnsrr` or `tasks.<svc>` for clients that do their own load balancing (databases, gRPC); use the VIP for simple HTTP.
- Put an external load balancer in front of ingress for TLS, health checks and client IP preservation.
- Keep three or five managers across failure domains so network control survives a zone loss.

## 10. Common Anti-Patterns / Mistakes

- Treating overlay as a security boundary without enabling encryption or locking down the underlay.
- Running a two-node "cluster" with one manager and expecting network state to survive its loss.
- Publishing every service through the ingress mesh and then wondering why client IPs are lost.
- Using `--attachable` overlays as a convenient shared network for developer ad hoc containers on production nodes.
- Letting two overlays or a VPN share an overlapping CIDR.
- Using overlay for a single-host Compose project, where a user-defined bridge is faster and simpler ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)).
- Debugging at the container layer only, never capturing UDP 4789 on the host.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does an overlay network solve, and what does it need to work?"_
**Model answer:** A bridge network only spans one host. An overlay makes containers on separate hosts share one virtual subnet so they reach each other by IP or service name. It encapsulates container traffic in VXLAN (UDP 4789) between hosts and needs a cluster control plane; in Docker that means Swarm mode must be initialized. The hosts must be able to reach each other on TCP 2377 (managers), TCP and UDP 7946 and UDP 4789. Create one with `docker network create -d overlay`, adding `--attachable` if standalone containers should join.
_What the interviewer is probing for:_ Knowing the purpose, the Swarm dependency and the basic port list.

**🎯 Intermediate:** _"Trace a packet from a container on Host A to a container on Host B over an overlay."_
**Model answer:** The source container sends to the destination's overlay IP. The frame crosses its veth into the per-network namespace and `br0`. Because the destination MAC lives on another host, the bridge forwards to `vxlan0`, which looks up the remote VTEP in the FDB (programmed from the daemons' gossip), wraps the frame with a VXLAN header carrying the network's VNI, and sends it as UDP 4789 from Host A's IP to Host B's IP across the underlay. Host B's `vxlan0` decapsulates, `br0` delivers to the destination veth. ARP is answered locally from gossip-programmed entries rather than being broadcast. Total overhead is roughly 50 bytes per packet, hence the 1450 MTU.
_What the interviewer is probing for:_ A real mental model of encapsulation, VTEP, FDB and the control plane versus data plane split.

**🎯 Senior:** _"After a firewall change, a Swarm service works on its own node but times out from other nodes, and only for large responses. Diagnose it."_
**Model answer:** Two hypotheses: blocked or partly blocked overlay ports and an MTU problem. Large-only failures point to MTU or fragmentation. I would capture on both hosts with `tcpdump -ni eth0 udp port 4789` to see whether encapsulated packets arrive, check for ICMP fragmentation-needed being dropped, and test `ping -M do -s 1422` between containers. If a new tunnel or VPN reduced path MTU, I would set `com.docker.network.driver.mtu` lower on the network (requiring recreation) or fix the underlay. I would also verify 7946 TCP+UDP, since broken gossip yields stale FDB entries, and compare `docker network inspect` peers on each node. The fix is verified with a large transfer, not just a ping.
_What the interviewer is probing for:_ Systematic, layered debugging, MTU awareness, and knowing where to capture packets.

**🎯 Architect:** _"Design networking for a 40-node Docker Swarm hosting multiple tenants, some regulated. What do you decide about overlays?"_
**Model answer:** One overlay per tenant and per tier, created with explicit non-overlapping subnets from a central IPAM plan, `--internal` for data tiers, and `--opt encrypted` for regulated tenants whose traffic crosses shared infrastructure, accepting the CPU cost. Underlay in a dedicated VLAN or VPC subnet with security groups permitting only 2377 (managers), 7946 and 4789 and ESP between nodes. Five managers across three zones; workers labeled by zone, with placement constraints keeping tenants on their own networks. Ingress via an external load balancer to preserve client IPs and terminate TLS, with `mode=host` or dnsrr for latency-sensitive services. I would load-test VXLAN throughput, plan MTU, monitor conntrack and gossip health, and document the exit path: beyond this scale or for richer policy, move to Kubernetes with a CNI that offers network policy.
_What the interviewer is probing for:_ Multi-tenant isolation design, encryption trade-offs, IPAM discipline and honest awareness of Swarm's limits.

## 12. Common Misconceptions

- "Overlay networks are encrypted." Not by default; you must opt in.
- "Overlay works with plain Docker Engine, no Swarm." Overlay needs the Swarm control plane.
- "The ingress mesh preserves the client IP." It source-NATs unless you publish in host mode.
- "Overlay containers are reachable from outside by their overlay IP." The overlay is private to the cluster; you must publish ports or use a gateway.
- "Macvlan and overlay are interchangeable." Macvlan exposes containers on the physical LAN with no tunnel and no cluster-wide service discovery.
- "Overlay networks exist on every node immediately." They materialize on a node only when a task or container there joins.

## 13. 🔑 Key Takeaways

- Overlay = VXLAN encapsulation (UDP 4789) plus a gossiped control plane, requiring Swarm mode.
- Open TCP 2377, TCP+UDP 7946, UDP 4789 (and ESP for encryption) between nodes only.
- Overlay MTU is about 1450; nested tunnels need explicit lower MTU.
- Encryption is opt-in (`--opt encrypted`); the underlay is otherwise trusted.
- Service names resolve to a VIP (IPVS-balanced); `tasks.<svc>` and `dnsrr` expose task IPs.
- Plan subnets explicitly to avoid overlap, and segment tiers on separate overlays.

## 14. Related Concepts & What's Next

Related: driver overview ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), bridge internals ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), DNS ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), NAT and iptables ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), segmentation ([§49](Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)), Swarm ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)) and the move to Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)). Next, [§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md) assembles the toolbox used to debug everything in this part, overlays included.

**Next Section:** [§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md) — `Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md`
