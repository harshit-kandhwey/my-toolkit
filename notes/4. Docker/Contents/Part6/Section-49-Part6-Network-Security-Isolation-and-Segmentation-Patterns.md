# Section 49 (Part 6): Network Security: Isolation and Segmentation Patterns

## 1. Definition

**Plain language:** Docker networking is open by default: every container on a bridge can talk to every other container on it, and to the outside world. Network security means shrinking that to only the paths the application needs, using separate networks per tier, internal-only networks, careful port publishing, host firewall rules and, where needed, encryption.

**Precise definition:** Segmentation in Docker is built from these controls: (a) **multiple user-defined networks**, with a container attached only to those it must use (separate bridges are separate L2 domains with iptables rules dropping cross-bridge traffic); (b) **`--internal` networks**, which have no gateway to the outside and no published-port path; (c) **bind-address restrictions** on `-p`; (d) **inter-container connectivity** (`com.docker.network.bridge.enable_icc=false`) on a bridge; (e) **egress control** via `DOCKER-USER` iptables/nftables rules or a proxy; (f) **host firewall** integration; (g) **encrypted overlay** (`--opt encrypted`) between hosts; and (h) **socket and privilege hygiene** (`--cap-drop`, no `--network host`, no Docker socket mounts). None of these replace application-layer authentication; they reduce blast radius when something is compromised.

> 💡 **Tip:** Think "which containers must be able to open a connection to which others, on which port". Everything else should be impossible by construction, not by convention.

## 2. Why This Matters

- A flat network turns one compromised container (for example, a vulnerable web front end) into a launch pad against the database, the cache and any admin endpoint.
- A published port is an exposed attack surface; the classic mistake is a database published on `0.0.0.0`.
- Docker manipulates iptables itself, so host firewall rules written in `ufw` or `firewalld` often silently fail to restrict published container ports.
- Regulatory and customer requirements (PCI-DSS, SOC 2, internal zero-trust standards) ask for demonstrable segmentation, and Compose gives a clear, reviewable way to express it.
- Data exfiltration and command-and-control need outbound access; blocking egress turns many compromises into non-events.

## 3. Prerequisites and Dependencies

Understand network drivers ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), bridges and user-defined networks ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), DNS ([§44](Section-44-Part6-Container-DNS-and-Service-Discovery.md)), publishing and the iptables chains ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), overlays ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)) and the communication patterns in [§48](Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md). The wider security model, capabilities, seccomp and secrets live in Part 8 ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md), [§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)). Compose syntax for networks is in [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md).

## 4. Architecture / Conceptual Diagram

```text
                 Internet / LAN
                      │
                      ▼  :443 (only published port, bound to a chosen interface)
              ┌───────────────┐
              │    proxy      │  networks: frontend
              └───────┬───────┘
                      │ frontend (bridge)           ← proxy ◄──► web only
              ┌───────▼───────┐
              │     web       │  networks: frontend, backend
              └───────┬───────┘
                      │ backend (bridge, internal: true)   ← no route out
              ┌───────▼───────┐     ┌───────────────┐
              │     api       │◄───►│    worker     │  networks: backend, data
              └───────┬───────┘     └───────┬───────┘
                      │ data (bridge, internal: true)
              ┌───────▼───────┐     ┌───────────────┐
              │      db       │     │    cache      │  networks: data only
              └───────────────┘     └───────────────┘

   Egress: api ──► egress-proxy (allow-list) ──► external SaaS API
   Blocked by design:  proxy ✗ db     web ✗ db     db ✗ internet     cache ✗ web
```

| Control | What it restricts | Layer |
|---|---|---|
| Separate networks | who can even route to whom | L2/L3 |
| `internal: true` | any path to or from outside the host | L3 |
| `-p 127.0.0.1:...` | which host interface accepts connections | L4 |
| `enable_icc=false` | traffic between containers on one bridge | L3 |
| `DOCKER-USER` rules | arbitrary allow/deny, including egress | L3/L4 |
| `--opt encrypted` | confidentiality of overlay traffic | L3 (IPsec/ESP) |
| App auth, TLS | who may use the service | L7 |

## 5. Hands-On

### 5.1 Tiered Networks in Compose

```yaml
services:
  proxy:
    image: nginx:1.27-alpine
    ports:
      - "443:443"
    networks: [frontend]

  web:
    image: myorg/web:1.0
    networks: [frontend, backend]

  api:
    image: myorg/api:1.0
    networks: [backend, data]

  db:
    image: postgres:16-alpine
    networks: [data]

networks:
  frontend: {}
  backend:
    internal: true
  data:
    internal: true
```

```bash
docker compose up -d
docker compose exec proxy sh -c 'nc -zv -w2 db 5432' ; echo "exit=$?"
docker compose exec api   sh -c 'nc -zv -w2 db 5432' ; echo "exit=$?"
docker compose exec db    sh -c 'wget -q -T2 -O- https://example.com >/dev/null' ; echo "exit=$?"
```

```text
nc: bad address 'db'
exit=1
db (172.20.0.2:5432) open
exit=0
wget: bad address 'example.com'
exit=1
```

`proxy` is not on `data`, so `db` does not even resolve for it (embedded DNS only answers for networks the asker shares). `db` is on an internal network, so it has no default route to the internet.

### 5.2 Verifying Isolation Instead of Trusting It

```bash
docker network inspect -f '{{.Name}} internal={{.Internal}}' $(docker network ls -q)
docker inspect -f '{{range $n,$v := .NetworkSettings.Networks}}{{$n}} {{end}}' app-db-1
docker run --rm --network app_frontend curlimages/curl -s --max-time 2 http://db:5432 || echo blocked
```

```text
app_data internal=true
app_frontend internal=false
bridge internal=false
app_data
blocked
```

Make a check like this part of CI or a post-deploy smoke test: an isolation claim that is never tested decays silently.

### 5.3 Publishing Safely: Bind Address and Defaults

```bash
docker run -d --name admin -p 127.0.0.1:9000:9000 myorg/admin:1.0     # host loopback only
docker run -d --name pub   -p 10.0.0.5:443:443   myorg/edge:1.0       # one specific NIC
ss -ltn | grep -E ':9000|:443'
```

```text
LISTEN 0 4096 127.0.0.1:9000  0.0.0.0:*
LISTEN 0 4096 10.0.0.5:443    0.0.0.0:*
```

A daemon-wide safer default is `"ip": "127.0.0.1"` in `daemon.json` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)), so a bare `-p 8080:80` binds loopback unless the operator writes an explicit address.

### 5.4 Disabling Inter-Container Communication on a Bridge

```bash
docker network create \
  --opt com.docker.network.bridge.enable_icc=false \
  isolated
docker run -d --name a --network isolated alpine sleep 600
docker run -d --name b --network isolated alpine sleep 600
docker exec a ping -c1 -W1 b ; echo "exit=$?"
```

```text
PING b (172.21.0.3): 56 data bytes

--- b ping statistics ---
1 packets transmitted, 0 packets received, 100% packet loss
exit=1
```

Name resolution still works but packets are dropped between peers. Traffic to the gateway and published ports continues. Use this for hosting many untrusting single-purpose containers on one bridge; for application stacks, separate networks are clearer.

### 5.5 Egress Control With `DOCKER-USER`

Docker evaluates the `DOCKER-USER` chain first for forwarded traffic and never overwrites it, so it is the supported place for operator rules.

```bash
# Allow replies, allow the app subnet to reach one external API, drop the rest of its egress
sudo iptables -I DOCKER-USER -s 172.22.0.0/16 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo iptables -I DOCKER-USER -s 172.22.0.0/16 -d 203.0.113.10 -p tcp --dport 443 -j ACCEPT
sudo iptables -A DOCKER-USER -s 172.22.0.0/16 ! -d 172.22.0.0/16 -j DROP
sudo iptables -L DOCKER-USER -n -v --line-numbers
```

```text
Chain DOCKER-USER (1 references)
num  pkts bytes target  prot opt in  out  source          destination
1    0    0     ACCEPT  tcp  --  *   *    172.22.0.0/16   203.0.113.10   tcp dpt:443
2    0    0     ACCEPT  all  --  *   *    172.22.0.0/16   0.0.0.0/0      ctstate RELATED,ESTABLISHED
3    0    0     DROP    all  --  *   *    172.22.0.0/16  !172.22.0.0/16
```

Match the rule to the bridge by interface (`-i br-<id>`) or a fixed subnet (`docker network create --subnet 172.22.0.0/16`). Rules in a chain are order-dependent: insert allow rules above the final drop. On hosts using nftables natively, translate to an equivalent `forward` hook rule; Docker 28 also tightens default handling of unpublished-port access from outside the host, but do not depend on version defaults for policy. Test these rules on a throwaway VM or in a disposable network namespace before applying them to a real machine.

### 5.6 Encrypted Overlay Traffic Between Hosts

```bash
docker network create -d overlay --opt encrypted --attachable secure-overlay
```

With `--opt encrypted`, data-plane traffic between Swarm nodes is wrapped in IPsec (ESP) tunnels, at a CPU cost. Open UDP 4789 (VXLAN), TCP/UDP 7946 and TCP 2377 only between cluster nodes ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)); IP protocol 50 (ESP) must also pass. Control-plane traffic is always encrypted; only the data plane is opt-in.

### 5.7 Reducing What a Compromised Container Can Do on the Network

```bash
docker run -d --name hardened \
  --network backend \
  --cap-drop ALL --cap-add NET_BIND_SERVICE \
  --read-only --tmpfs /tmp \
  --security-opt no-new-privileges \
  --user 10001:10001 \
  myorg/api:1.0
```

Dropping `NET_RAW` (part of the default set) blocks raw sockets, which prevents ARP spoofing and many scanning tools inside the container; dropping `NET_ADMIN` (never default) prevents reconfiguring interfaces and iptables. See [§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md) for the capability model.

### 5.8 A Shared Docker Socket Is Not Network Security

```bash
# Anti-example: do NOT do this in production
docker run -v /var/run/docker.sock:/var/run/docker.sock some-dashboard
```

Network segmentation is moot if a container can talk to the daemon: the API can create a privileged container on the host network. If an application must read container metadata, put a filtering socket proxy in front of the socket, allow only `GET /containers/json`-style calls, and attach the proxy on a dedicated internal network ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).

## 6. Production Usage Notes

- **Model tiers as networks:** edge, app, data, plus an optional management network. Attach each service to the minimum set; only a gateway-style service spans two tiers.
- **Mark backends `internal: true`** and give the one component that needs outbound access (egress proxy, payment client) an additional non-internal network.
- **Publishing:** one or two edge ports. Admin UIs, metrics endpoints and databases are published to `127.0.0.1` (reached via SSH tunnel or VPN) or not at all. Metrics scraping should happen over a shared monitoring network ([§87](../Part12/Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)).
- **Host firewall:** treat `DOCKER-USER` as policy and keep it under configuration management. Remember that `ufw allow/deny` does not govern published container ports; use `ufw-docker`-style rules or `DOCKER-USER` directly.
- **Egress allow-lists** through an HTTP(S) proxy (squid, envoy) are easier to audit than IP rules for SaaS endpoints whose addresses change; set `HTTP_PROXY`/`HTTPS_PROXY` and block direct egress at the network layer.
- **TLS everywhere across hosts**, and mutual TLS for sensitive service-to-service calls. Overlay encryption protects the wire but does not authenticate the application.
- **Cloud environments:** pair container segmentation with VPC security groups and network policy at the orchestrator level; Docker bridges do not replace them. In Kubernetes, `NetworkPolicy` expresses the same intent.
- **Auditing:** record `docker network inspect` output and the Compose file in version control; diff them in review. Alert on new published ports or containers started with `--network host` or `--privileged`.
- **Rootless mode** reduces daemon-level blast radius but changes networking (user-space proxy for ports, no real iptables control); factor that into design ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)).

## 7. Security Considerations

- **Default posture is permissive.** Same-bridge peers are mutually reachable and outbound is open; segmentation is something you add.
- **Bypassed host firewalls.** Docker inserts DNAT and FORWARD accept rules ahead of most user rules; a published port may be reachable from the internet even though `ufw status` shows it denied. Verify with an external port scan from another machine, not by reading the firewall config.
- **`--network host`, `--privileged` and the Docker socket** each defeat network segmentation entirely. Disallow them with policy, admission checks, or a daemon authorization plugin.
- **ARP and DNS spoofing inside a bridge.** With `NET_RAW`, a compromised container can spoof ARP for its neighbours on the same bridge; dropping `NET_RAW` and splitting networks mitigates it.
- **Cloud metadata endpoints.** Containers on cloud VMs can reach `169.254.169.254` through the host; block it in `DOCKER-USER` or enforce IMDSv2 with a hop limit of 1 so containers cannot obtain the host's instance credentials.
- **Lateral movement via shared services.** A monitoring agent or log shipper attached to every network is itself a bridge across segments; give it read-only, narrowly scoped access and its own network.
- **Information leaks from names.** Embedded DNS only resolves names on shared networks, so isolation also hides topology; do not undermine it with `--add-host` entries pointing at internal IPs.
- **Secrets in transit.** Never send credentials over an unencrypted cross-host path; use TLS or an encrypted overlay and avoid environment-variable secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Supply chain:** a compromised image is already inside your trust boundary; segmentation limits what it reaches but scanning and signing prevent it ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Service on an `internal` network cannot call an external API | Internal networks have no gateway | Attach it also to a normal network, or route via an egress proxy on both |
| Published port unreachable from another machine | Bound to `127.0.0.1`, or host/cloud firewall blocks it | Check `ss -ltn` and `docker port`; fix bind address or firewall |
| Published port reachable despite `ufw deny` | Docker's iptables rules precede ufw | Restrict in `DOCKER-USER`, or bind to loopback |
| Container cannot resolve a peer after segmentation | Peer not on a shared network | Add the specific network to both services, not a broad one |
| `DOCKER-USER` rule has no effect | Wrong order, or traffic matched an earlier ACCEPT; wrong subnet or interface | `iptables -L DOCKER-USER -n -v --line-numbers`; move rule up; use the right `-i`/`-s` |
| Rules vanish after reboot | `iptables` rules are not persistent | Persist via `iptables-persistent`/`nftables.conf` or a systemd unit that reapplies |
| `enable_icc=false` also broke app traffic | App relies on direct peer calls on that bridge | Use separate networks per tier instead, or use published/linked paths deliberately |
| Overlay containers cannot communicate across nodes | Ports 4789/7946/2377 or ESP blocked between nodes | Open them node-to-node; verify with `docker node ls` and packet capture ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)) |
| Healthcheck or scraper fails after moving DB to `internal` | Monitoring host not on that network | Join the scraper to the network (read-only role) or use a metrics proxy |
| IPv6 traffic bypasses IPv4 rules | IPv6 enabled on the network, rules written for IPv4 only | Mirror rules with `ip6tables`/nftables or leave IPv6 off |

## 9. Best Practices

- Default-deny mindset: start from isolated networks and add only the connections the design requires.
- One network per trust tier; attach services to the minimum number of networks.
- `internal: true` for every network that has no business reaching outward.
- Bind published ports to explicit interfaces; set a loopback default in `daemon.json`.
- Enforce egress with `DOCKER-USER` or a proxy; document every permitted destination and its owner.
- Drop capabilities (especially `NET_RAW`), run read-only and non-root ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- Prohibit `--network host`, `--privileged` and socket mounts in production by policy.
- Encrypt cross-host traffic (TLS, mTLS, encrypted overlay) and keep node-to-node ports firewalled.
- Test isolation with negative tests (this connection must fail) in CI and after each change.
- Keep network layout in version control and review changes like code.

## 10. Common Anti-Patterns / Mistakes

- Everything on one default network "because it works".
- Publishing databases, message brokers or admin consoles on `0.0.0.0`.
- Trusting `ufw` to protect published container ports.
- Using the Docker socket or `--privileged` to solve a networking problem.
- Adding a catch-all "shared" network that every service joins, recreating a flat network.
- Relying on obscurity of container names or ports as a security measure.
- Disabling ICC but leaving every container on the default bridge with the host's full egress.
- Setting `internal: true` on a network and then adding `extra_hosts` or a proxy that quietly reconnects it.
- Writing IPv4-only firewall rules on dual-stack networks.
- No negative tests: assuming segmentation works because the Compose file says so.

## 11. Interview Questions

**🎯 Beginner:** _"How would you stop a web container from connecting directly to the database container in a Compose application?"_
**Model answer:** Put them on different networks. Define a `frontend` network for the proxy and web, and a `backend` network for the database, and attach the API to both so it is the only bridge between tiers. Containers on networks they do not share cannot route to each other and cannot even resolve each other's names via Docker's embedded DNS. Mark the database network `internal: true` so it also has no outbound path. Finally, verify with a connection attempt from the web container, which must fail.
_What the interviewer is probing for:_ That segmentation is done by network membership, and the habit of testing it.

**🎯 Intermediate:** _"You blocked port 5432 with `ufw deny`, yet a scan from another machine shows PostgreSQL open. Why, and what do you do?"_
**Model answer:** Published ports are implemented with iptables DNAT and FORWARD rules that Docker inserts ahead of the chains `ufw` manages, so the traffic is accepted before `ufw` sees it. The right fixes are to not publish the port at all (other containers use the service name on a private network), or to publish it on `127.0.0.1`, or to add restrictions in the `DOCKER-USER` chain, which Docker evaluates first and never rewrites. I would also set a loopback default publish address in `daemon.json` and verify with an external scan rather than reading firewall output.
_What the interviewer is probing for:_ Understanding of how Docker interacts with the host firewall and the supported control point.

**🎯 Senior:** _"A compromised web container was used to scan the internal network and exfiltrate data. Redesign the networking to limit both lateral movement and egress."_
**Model answer:** Split into tiers: the web container only joins the frontend and an API-facing network, not the data network; the data network is `internal: true`. Drop `NET_RAW` and all other unneeded capabilities, run read-only and non-root, and set `no-new-privileges`, so scanning tools and ARP tricks are limited. For egress, remove the default route for the web tier by placing it on internal networks and give outbound access only to an egress proxy with a destination allow-list, backed by `DOCKER-USER` rules that drop direct outbound traffic from the app subnets. Block the cloud metadata address. Add monitoring of connection attempts and DNS queries from those subnets for alerting, and add CI negative tests so the posture cannot regress.
_What the interviewer is probing for:_ Defence in depth: segmentation, capability reduction, egress control and detection, not just one control.

**🎯 Architect:** _"Define the container network security standard for a 40-service platform running across several hosts with mixed trust levels and compliance requirements."_
**Model answer:** I would set a zone model (edge, application, data, management) with a written allow-matrix of permitted flows by port, implemented as networks per zone per application, `internal` wherever outbound is unnecessary, and one reviewed egress path. Cross-host traffic uses an encrypted overlay or, preferably, an orchestrator with network policy and mTLS identity so rules follow workloads rather than IPs. The standard bans host networking, privileged containers and socket mounts without an exception process, requires non-root, dropped capabilities and read-only roots, and sets daemon defaults (loopback publish address, userland-proxy and ICC settings, log and userns configuration) via configuration management. Evidence matters for compliance, so Compose and network definitions are version-controlled, policy is enforced in CI with linting and runtime checks, isolation is verified by automated negative tests, and flow logs are retained. I would also state clearly that Docker bridges are a single-host mechanism and that at scale Kubernetes NetworkPolicy or a service mesh is the long-term enforcement layer.
_What the interviewer is probing for:_ Policy as a model (zones and flow matrix), enforcement and evidence, and an honest view of where Docker-native controls stop.

## 12. Common Misconceptions

- "Containers are isolated from each other by default." Isolation is at the process, filesystem and namespace level; peers on a bridge can still connect.
- "`ufw`/`firewalld` rules protect published ports." Docker's rules typically take precedence.
- "`internal: true` blocks container-to-container traffic." It blocks external connectivity; peers on the same internal network still communicate.
- "Not publishing a port makes a service private." Anything on the same network can still reach it; privacy comes from network membership.
- "An encrypted overlay replaces TLS." It protects the wire between nodes, not application identity or the host-local path.
- "Segmentation is only for big deployments." One extra network in a three-container Compose file already removes a whole class of lateral movement.

## 13. 🔑 Key Takeaways

- Segment by network membership: one network per tier, minimum attachments, `internal: true` for backends.
- Publish as little as possible and bind to specific interfaces; docker rules can bypass `ufw`.
- Use `DOCKER-USER` (or an egress proxy) for firewall policy and egress allow-lists.
- Drop capabilities, run non-root and read-only, and never mount the Docker socket casually.
- Encrypt cross-host traffic and keep node ports firewalled.
- Test isolation with negative tests; keep network design in version control.

## 14. Related Concepts & What's Next

Related: network drivers ([§42](Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), bridges ([§43](Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), port publishing and iptables ([§45](Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), overlays ([§46](Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), troubleshooting ([§47](Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)), communication patterns ([§48](Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md)), the container security model ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)) and capabilities ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)). This closes Part 6 on networking. Part 7 turns to the other half of running real workloads, persistent data, starting with storage drivers and overlay2 internals in [§50](../Part7/Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md).

**Next Section:** [§50](../Part7/Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md) — `Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md`
