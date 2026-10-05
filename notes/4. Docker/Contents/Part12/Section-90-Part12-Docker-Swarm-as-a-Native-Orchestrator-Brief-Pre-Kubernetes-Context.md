# Section 90 (Part 12): Docker Swarm as a Native Orchestrator (Brief, Pre-Kubernetes Context)

## 1. Definition

**Plain language:** Swarm mode turns several Docker hosts into one pool. You describe a *service* ("run 3 copies of this image, publish port 80") and Swarm keeps that true: it places the copies on nodes, replaces them when they die, and load-balances traffic across them. It is built into `dockerd`; there is nothing extra to install.

**Precise definition:** Swarm mode (SwarmKit, integrated into Docker Engine since 1.12) is a Raft-based clustered control plane. **Manager** nodes hold the cluster state in a replicated Raft log (an embedded store), run the scheduler, orchestrator, dispatcher and CA, and expose the API. **Worker** nodes only run tasks. The unit you declare is a **service**; the scheduler turns it into **tasks** (one task = one container slot on one node). Services come in two modes: `replicated` (N tasks, placed by the scheduler) and `global` (one task per eligible node). Nodes talk over mutually authenticated TLS with certificates the managers issue and rotate automatically. Swarm provides an encrypted-capable `overlay` network ([§46](../Part6/Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), a routing mesh for published ports, built-in DNS service discovery, rolling updates, and `secrets`/`configs` objects.

> 💡 **Tip:** "Swarm mode" (built into the engine, `docker swarm`, `docker service`, `docker stack`) is not the same as the retired standalone "Docker Swarm" (classic) product from 2014-2016, which was a separate container image. Almost everything you read today means swarm mode.

## 2. Why This Matters

- It is the shortest path from "one Docker host plus Compose" to "several hosts with self-healing and rolling updates," using tools you already know.
- It explains where Kubernetes ideas came from (desired state, reconciliation, services, rolling updates) and makes [§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md) easier to reason about.
- Many small teams and homelabs still run Swarm in production because the operational surface is tiny.
- Legacy estates and the DCA exam still include Swarm (see [§7](../Part1/Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md) and [§100](../Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)); interviewers use it to test whether you understand orchestration concepts independent of Kubernetes.
- It is also a frank lesson in ecosystem risk: Swarm still works and is maintained, but feature investment slowed sharply after Docker Inc. refocused on developer tooling and Mirantis took over the enterprise product line.

## 3. Prerequisites and Dependencies

Requires the engine architecture ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), Compose files ([§34](../Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), [§35](../Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), networking basics including overlay and port publishing ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md), [§46](../Part6/Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), health checks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md), [§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)) and resource limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md), [§89](Section-89-Part12-Resource-Management-at-Scale.md)). Network prerequisites between nodes: TCP 2377 (manager API/Raft), TCP+UDP 7946 (gossip), UDP 4789 (VXLAN data plane); IP protocol 50 (ESP) if overlay encryption is on. Secrets design builds on [§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md).

## 4. Architecture / Conceptual Diagram

```text
                    docker service create / docker stack deploy
                                    │
                                    ▼
   ┌──────────────────────── MANAGER NODES (odd count: 3 or 5) ────────────────────────┐
   │  ┌──────────┐   Raft log (desired state: services, secrets, configs, networks)    │
   │  │ Leader   │◄────────replicates────────►  Follower      Follower                 │
   │  └────┬─────┘                                                                      │
   │       │ API ► Orchestrator ► Allocator ► Scheduler ► Dispatcher   (+ internal CA)  │
   └───────┼────────────────────────────────────────────────────────────────────────────┘
           │  tasks assigned over mTLS (gRPC)
           ▼
   ┌──────────── WORKER NODE A ───────────┐   ┌──────────── WORKER NODE B ───────────┐
   │ agent ► dockerd ► containerd ► runc  │   │ agent ► dockerd ► containerd ► runc  │
   │  task web.1  task web.3              │   │  task web.2  task db.1               │
   └──────────────┬───────────────────────┘   └───────────────┬──────────────────────┘
                  └──── overlay network (VXLAN, UDP 4789) ◄───┘
                          ▲
   client ──► any node:80 │  ingress routing mesh (IPVS) forwards to a healthy task,
                            even on a node that runs none

  Service lifecycle:   desired state (replicas=3) ──► reconcile loop ──► observed state
                       task states: new ► pending ► assigned ► running ► shutdown/failed
```

- **Desired-state reconciliation:** if a node dies, tasks on it are marked failed and rescheduled elsewhere; you never "restart" anything by hand.
- **Raft quorum:** with N managers the cluster tolerates (N-1)/2 failures. Three managers tolerate one; five tolerate two. Losing quorum freezes *changes* but running tasks keep running.
- **Ingress routing mesh:** a published port opens on every node; IPVS forwards to any healthy task. `mode=host` publishing bypasses the mesh and binds only where the task runs.
- **Stack:** a Compose-format file with a `deploy:` section, deployed by `docker stack deploy`.

## 5. Hands-On

All commands below change cluster state on the machine where they run. Practise on a throwaway VM, a Docker-in-Docker lab, or a disposable single-node swarm, never on a host whose containers you care about.

### 5.1 Initialise a Swarm and Join Nodes

```bash
docker swarm init --advertise-addr 192.168.1.10
docker swarm join-token worker
docker swarm join-token manager
docker node ls
```

```text
Swarm initialized: current node (x1y2z3) is now a manager.
To add a worker to this swarm, run the following command:
    docker swarm join --token SWMTKN-1-... 192.168.1.10:2377

ID            HOSTNAME   STATUS  AVAILABILITY  MANAGER STATUS  ENGINE VERSION
x1y2z3 *      node1      Ready   Active        Leader          27.3.1
```

On the other hosts run the printed `docker swarm join ...` line. Treat the token like a credential; rotate it with `docker swarm join-token --rotate worker`.

### 5.2 Create and Scale a Service

```bash
docker service create --name web --replicas 3 -p 8080:80 \
  --limit-memory 128m --reserve-memory 64m nginx:1.27
docker service ls
docker service ps web
docker service scale web=5
docker service inspect --pretty web
```

```text
ID        NAME   MODE        REPLICAS  IMAGE        PORTS
k9ab...   web    replicated  3/3       nginx:1.27   *:8080->80/tcp

NAME    IMAGE        NODE    DESIRED STATE  CURRENT STATE
web.1   nginx:1.27   node1   Running        Running 20 seconds ago
web.2   nginx:1.27   node2   Running        Running 19 seconds ago
web.3   nginx:1.27   node3   Running        Running 19 seconds ago
```

`curl http://<any-node-ip>:8080` works from any node because of the routing mesh.

### 5.3 Rolling Update and Rollback

```bash
docker service update --image nginx:1.27.2 \
  --update-parallelism 1 --update-delay 10s \
  --update-failure-action rollback --update-order start-first web
docker service rollback web
```

`--update-order start-first` starts the new task before stopping the old one, which gives zero-downtime replacement when combined with a health check (the pattern is expanded in [§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)). `--update-failure-action rollback` reverts automatically when new tasks fail their health check or exit.

### 5.4 A Stack File

```yaml
# stack.yml
services:
  api:
    image: registry.example.com/api:1.4.0
    networks: [backend]
    secrets: [db_password]
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 20s
    deploy:
      replicas: 3
      update_config:
        parallelism: 1
        delay: 10s
        order: start-first
        failure_action: rollback
      rollback_config:
        parallelism: 1
      restart_policy:
        condition: on-failure
        max_attempts: 3
      resources:
        limits:   { cpus: "0.50", memory: 256M }
        reservations: { cpus: "0.25", memory: 128M }
      placement:
        constraints: [node.role == worker]
networks:
  backend:
    driver: overlay
    driver_opts:
      encrypted: "true"
secrets:
  db_password:
    external: true
```

```bash
printf 's3cr3t' | docker secret create db_password -
docker stack deploy -c stack.yml shop
docker stack services shop
docker stack ps shop --no-trunc
```

Notes on how `docker stack deploy` differs from `docker compose up`: `build:` is ignored (images must already be in a registry reachable by every node), `depends_on` is ignored, `container_name` is unsupported, and `deploy:` is honoured. Secrets appear as files at `/run/secrets/db_password` inside the task.

### 5.5 Node Maintenance and Lost Quorum

```bash
docker node update --availability drain node3
docker node update --label-add disk=ssd node2
docker swarm init --force-new-cluster --advertise-addr 192.168.1.10   # last resort, majority of managers permanently lost
```

Draining reschedules a node's tasks elsewhere. `--force-new-cluster` keeps services and secrets but discards the other managers; back up `/var/lib/docker/swarm` as in [§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md).

## 6. Production Usage Notes

- **Managers:** run 3 (or 5) dedicated managers across failure domains; never an even number. Keep managers off the app workload path (`docker node update --availability drain` on managers) in larger clusters. Keep manager latency low: Raft is sensitive to slow disks and WAN links.
- **Secrets and configs** are immutable objects; to rotate, create `db_password_v2`, update the service with `--secret-rm`/`--secret-add`, then remove the old one.
- **Autolock** (`docker swarm init --autolock`) encrypts the Raft keys at rest; you must supply the unlock key after a manager restart, so store it in a vault, not on the node.
- **Image distribution:** every node pulls images itself. Use a registry reachable by all nodes and `--with-registry-auth` on `docker service update` / `stack deploy` so workers receive credentials ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)). Pin by digest for reproducibility.
- **Persistent data:** local volumes are node-local. Either pin stateful services with placement constraints or use a volume driver backed by shared storage ([§53](../Part7/Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md), [§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)). Swarm has no native PersistentVolume abstraction.
- **Ingress:** the routing mesh is simple but hides client source IP for mesh-published ports; put a reverse proxy (Traefik, nginx, HAProxy) in `mode: host` or global mode when you need real client addresses or L7 routing.
- **Observability:** run cAdvisor and a log shipper as `global` services ([§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md), [§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)).
- **Limits:** no operators/CRDs, no autoscaler, no first-class network policy, few managed offerings.

## 7. Security Considerations

- **mTLS by default:** node identities come from the manager CA; certificates rotate every 90 days by default (`docker swarm ca --cert-expiry`). Rotate the CA with `docker swarm ca --rotate` after a suspected compromise.
- **Join tokens are bearer credentials.** Possession of a *manager* token is cluster takeover; rotate after use, never commit to Git or paste in chat.
- **Manager API exposure:** TCP 2377 must be reachable only by cluster nodes. Never expose the Docker API socket or an unauthenticated TCP 2375 ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)). A manager can start privileged containers on any node, so manager compromise equals fleet compromise.
- **Overlay encryption** (`--opt encrypted`) uses IPsec ESP; it adds CPU cost and requires protocol 50 to pass firewalls. Without it, VXLAN traffic is plaintext on the wire.
- **Secrets** are encrypted in Raft and delivered to tasks over TLS as tmpfs files; they are far better than `ENV` ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)) but are readable by anyone who can exec into the task or any manager admin.
- **Not every `docker run` hardening flag exists for services** (`--privileged` is unsupported); verify support in your engine version ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md), [§60](../Part8/Section-60-Part8-Seccomp-Profiles.md)).
- Firewall published ports: the mesh opens them on *every* node.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Error response from daemon: This node is not a swarm manager` | Command run on a worker | Run on a manager, or promote with `docker node promote` |
| Tasks stuck in `Pending` with "no suitable node" | Constraints, resource reservations or platform not satisfiable | `docker service ps --no-trunc`; relax constraints or add capacity |
| Tasks stuck in `Preparing` | Image pull slow or failing on that node, missing registry auth | Check node's registry access; add `--with-registry-auth` |
| Service updates but old behaviour persists | Mutable tag (`latest`) cached on nodes | Deploy a unique tag or digest |
| Mesh port unreachable between nodes | UDP 4789 or TCP/UDP 7946 blocked | Open the inter-node ports, check cloud security groups |
| `rpc error: context deadline exceeded` / manager flapping | Raft latency, clock skew or disk stall | Check disk I/O, NTP and network; keep managers close together |
| "Quorum lost" (cannot change services) | Majority of managers down | Restore managers; last resort `--force-new-cluster` |
| Task restarts forever | Failing health check or app crash | `docker service logs`, tune `start_period`, set `max_attempts` |
| Stack ignores `build:` | Swarm does not build | Build and push in CI ([§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)) |

Useful commands: `docker service logs -f --tail 100 web`, `docker node inspect --pretty node1`, `docker network inspect ingress`, `docker events --filter type=service`.

## 9. Best Practices

- Use an odd number of managers (3 for most clusters) spread across failure domains; keep the count small.
- Declare everything in a version-controlled stack file; avoid imperative `docker service update` drift.
- Pin images by digest, give every service a health check and resource limits and reservations.
- Use `update_config.order: start-first` plus `failure_action: rollback` for safe rolling updates.
- Use secrets and configs rather than environment variables; version them by name.
- Label nodes and use placement constraints for stateful or hardware-bound services.
- Back up the swarm state and test restoring it ([§92](Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)).
- Decide early whether Swarm is a destination or a stepping stone, and document the exit criteria ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 10. Common Anti-Patterns / Mistakes

- Running two managers (losing either breaks quorum) or any even number.
- Heavy workloads on managers, starving Raft.
- Node-local volumes for stateful services without pinning them to a node.
- Assuming `docker stack deploy` behaves like `docker compose up`.
- Exposing the daemon on TCP without TLS, or 2377 to the internet.
- Relying on `latest` tags so nodes run different versions.
- Treating the routing mesh as a full L7 load balancer.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between a container, a task and a service in Docker Swarm?"_
**Model answer:** A container is the running process instance. A task is Swarm's scheduling unit: it binds one container to a slot in a service and to a specific node, and it has its own lifecycle states (pending, running, failed, shutdown). A service is the declared desired state: image, replica count or global mode, ports, networks, update policy. Swarm's orchestrator creates tasks to satisfy the service; if a task fails, a new task (and container) is created rather than the old one being restarted in place. You interact with the service, not the individual containers.
_What the interviewer is probing for:_ The desired-state model and the task abstraction.

**🎯 Intermediate:** _"You have three managers and two go down. What happens to running services and to your ability to operate the cluster?"_
**Model answer:** Raft needs a majority, which is two of three, so quorum is lost. Existing tasks on workers keep running and the routing mesh keeps serving, because the data plane does not depend on the leader. But the control plane is read-only: you cannot create, scale, update or remove services, and failed tasks will not be rescheduled. Recovery means bringing the managers back; if they are permanently lost, run `docker swarm init --force-new-cluster` on a surviving manager to rebuild a single-manager cluster from its Raft data, then re-add managers. This is why managers should be spread across failure domains and Raft state backed up.
_What the interviewer is probing for:_ Raft quorum maths and knowing control plane versus data plane.

**🎯 Senior:** _"Design a zero-downtime rolling update for a stateless API on Swarm, including what makes it safe."_
**Model answer:** Give the image a real `HEALTHCHECK`, because Swarm only treats a task as ready when the check passes. Configure `update_config` with `parallelism: 1`, `order: start-first` (surge a new task before stopping the old), a `delay` that exceeds the app's warm-up, and `failure_action: rollback` with a `monitor` period so a bad release reverts automatically. Set `stop_grace_period` and handle SIGTERM so in-flight requests drain. Ensure enough spare capacity for the surge via resource reservations, and confirm DB migrations are backward compatible (expand/contract) because old and new versions overlap. Deploy by immutable digest, and verify with `docker service ps` that no task flapped.
_What the interviewer is probing for:_ Health-check-gated updates, overlap safety, and rollback automation.

**🎯 Architect:** _"A client has ten services on Swarm and asks whether to migrate to Kubernetes. How do you advise?"_
**Model answer:** Frame it by requirements, not fashion. Swarm is cheap to run and fine for a small, stable estate with a team that knows Compose, but its ecosystem and managed-service support are thin and development has slowed. Kubernetes wins when they need autoscaling (HPA/cluster autoscaler), network policy, operators and CRDs, multi-tenant RBAC, managed cloud offerings, or hiring and tooling leverage. List the costs: manifest and Helm skills, a higher operational surface (mitigated by managed control planes), storage and ingress redesign. Propose an incremental path: standardise images, health checks, config and secrets handling first (these port directly), run a pilot workload on Kubernetes, and set exit criteria. If the estate is small and static, "stay on Swarm with a documented DR plan" is a legitimate answer.
_What the interviewer is probing for:_ Balanced, evidence-based technology advice and awareness of migration cost.

## 12. Common Misconceptions

- "Swarm is dead and unusable." It is still shipped in Docker Engine and works; it is simply less actively developed than Kubernetes.
- "`docker stack deploy` builds my images." It never builds.
- "The routing mesh means the container is on every node." Only the published port is; tasks run where scheduled.
- "More managers means more throughput." Extra managers add fault tolerance, not capacity, and slow down Raft.
- "Secrets are safe because they are encrypted." They protect at rest and in transit, but are plaintext files to anyone with exec access in the task.
- "Swarm autoscales." It scales only when you tell it to; there is no built-in autoscaler.

## 13. 🔑 Key Takeaways

- Swarm = Raft-backed managers + workers, declarative services, built-in overlay, mesh, secrets and rolling updates.
- Tasks are rescheduled, not repaired; desired state is continuously reconciled.
- Use 3 or 5 managers; quorum loss freezes changes but not running tasks.
- Rolling updates are only as safe as the health check, `start-first` order and rollback config.
- `stack deploy` is not `compose up`: no build, no `depends_on`, node-local volumes.
- Swarm is a valid small-scale orchestrator and a conceptual bridge to Kubernetes.

## 14. Related Concepts & What's Next

Related: engine and containerd ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)), Compose scaling ([§39](../Part5/Section-39-Part5-Scaling-Services-with-Compose.md)), overlay networks ([§46](../Part6/Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)), self-healing ([§88](Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), resource management ([§89](Section-89-Part12-Resource-Management-at-Scale.md)), and the Swarm-versus-Kubernetes decision ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)). Next, [§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md) generalises rolling updates into blue/green, canary and proxy-based zero-downtime patterns that work on Swarm, Compose and plain hosts.

**Next Section:** [§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md) — `Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md`
