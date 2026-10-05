# Section 39 (Part 5): Scaling Services with Compose

## 1. Definition

**Plain language:** Scaling in Compose means running more than one container of the same service on the same Docker host, for example three copies of `web` behind a reverse proxy. Compose creates and numbers the containers (`shop-web-1`, `shop-web-2`, `shop-web-3`) and Docker's embedded DNS lets other services reach all of them under the service name.

**Precise definition:** The replica count of a service is set in one of three places, in increasing precedence: the service's `deploy.replicas` attribute, the service's `scale` attribute, and the CLI flag `docker compose up --scale <service>=<N>`. All three create N containers from the same service definition on the **local** engine. Compose does not schedule across hosts, does not do rolling updates with `deploy.update_config`, and does not load-balance; it only creates replicas, gives each a unique name and IP, and registers them under the service's DNS name on the project networks. Anything that makes a service unique (a fixed `container_name`, a fixed host port, a single bind-mounted file with exclusive access) conflicts with `N > 1`.

> 💡 **Tip:** Scaling is only half the story. The other half is distributing traffic: either DNS round robin (clients resolve the service name) or a reverse proxy that discovers the replicas.

## 2. Why This Matters

- It is the quickest way to test horizontal-scaling behavior locally: statelessness, session handling, idempotency, health-checked load balancing.
- Single-node production stacks use it to use more than one CPU core for single-threaded runtimes (Node.js, Python workers) and to keep serving during a replica restart.
- It exposes design flaws early: hard-coded ports, `container_name`, local file state, in-memory sessions.
- Knowing where Compose stops (no cross-host scheduling, no rolling updates) is the line between "Compose is fine here" and "move to Swarm or Kubernetes".

## 3. Prerequisites and Dependencies

Requires the service model and project networks from [§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md), port publishing basics from the `docker run` deep dive ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), and health checks and `depends_on` conditions from [§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md). DNS behavior is detailed in [§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md), and publishing rules in [§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md). Resource limits applied per replica come from [§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md). Environment-specific replica counts use the override model from [§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md).

## 4. Architecture / Conceptual Diagram

```text
  docker compose up -d --scale web=3        (project "shop")

   host :80
     │ published port (only the proxy owns a host port)
     ▼
  ┌─────────────┐        network "shop_default" (user-defined bridge)
  │   proxy     │        embedded DNS at 127.0.0.11
  │ nginx/traefik│
  └──────┬──────┘
         │  resolves "web"  ──►  A records: 172.20.0.3, .4, .5
         │
   ┌─────┼───────────────┬───────────────────┐
   ▼     ▼               ▼                   ▼
 ┌───────────┐     ┌───────────┐       ┌───────────┐
 │ shop-web-1│     │ shop-web-2│       │ shop-web-3│   ◄── same image,
 │ 172.20.0.3│     │ 172.20.0.4│       │ 172.20.0.5│       same config,
 └─────┬─────┘     └─────┬─────┘       └─────┬─────┘       unique name/IP
       └─────────────────┴───────────────────┘
                         │
                         ▼
                 ┌──────────────┐
                 │ db (1 replica)│  ◄── shared state lives here, not in replicas
                 └──────────────┘

  What conflicts at N > 1:
   container_name: web          ► names must be unique
   ports: "8080:80"             ► only one container can bind host :8080
   shared writable single file  ► contention / corruption
```

- **Naming:** `<project>-<service>-<index>`, index starting at 1. `docker compose ps` shows them; `--index N` targets one.
- **Scale down** removes the highest-numbered replicas first; scale up adds the next free indexes.
- **DNS:** the service name resolves to all replica IPs; the order is rotated, so naive clients get round robin. Each replica is also reachable by its own container name.

## 5. Hands-On

### 5.1 A Scalable Service

```yaml
# compose.yaml
name: shop
services:
  web:
    image: nginxdemos/hello:plain-text
    expose: ["80"]               # container port only; no fixed host port
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://127.0.0.1/ >/dev/null || exit 1"]
      interval: 5s
      timeout: 2s
      retries: 5
    deploy:
      replicas: 2                # default count when no --scale is given
      resources:
        limits: { cpus: "0.50", memory: 128M }
```

```bash
docker compose up -d
docker compose ps
```

```text
NAME         IMAGE                        SERVICE   STATUS                  PORTS
shop-web-1   nginxdemos/hello:plain-text  web       Up 8 seconds (healthy)  80/tcp
shop-web-2   nginxdemos/hello:plain-text  web       Up 8 seconds (healthy)  80/tcp
```

### 5.2 Scaling Up and Down With the CLI

```bash
docker compose up -d --scale web=5          # CLI flag wins over deploy.replicas
docker compose ps --format "table {{.Name}}\t{{.Status}}"
docker compose up -d --scale web=2          # removes web-5, web-4, web-3
```

Existing replicas are kept when only the count changes (no recreate unless config changed). Always pass `--scale` on every `up` invocation, because a later plain `docker compose up -d` returns to the file's value (`scale`/`deploy.replicas`, or 1).

### 5.3 The `scale` Attribute

```yaml
services:
  worker:
    image: myorg/worker:2.3
    scale: 4                     # Compose Specification attribute
```

`scale` and `deploy.replicas` must agree if both are set; otherwise Compose reports a conflict. Pick one convention per project. A `--scale` flag overrides either.

### 5.4 The Fixed-Port Collision

```yaml
services:
  web:
    image: nginxdemos/hello:plain-text
    ports: ["8080:80"]
```

```bash
docker compose up -d --scale web=3
```

```text
Error response from daemon: driver failed programming external connectivity on endpoint shop-web-2 ...
Bind for 0.0.0.0:8080 failed: port is already allocated
```

Three ways out, from most to least recommended:

```yaml
# (a) Port range: one host port per replica
ports: ["8080-8082:80"]

# (b) Ephemeral host ports: Docker picks free ones
ports: ["80"]                    # find them with: docker compose port --index 2 web 80

# (c) Publish nothing on web; publish only the proxy (best)
expose: ["80"]
```

Note that a range must be at least as large as the replica count, and it ties your scale ceiling to the range size.

### 5.5 `container_name` Breaks Scaling

```yaml
services:
  web:
    image: nginxdemos/hello:plain-text
    container_name: web          # fixed name
```

```text
$ docker compose up -d --scale web=2
WARN service "web" is using container_name, which prevents scaling
```

Remove `container_name` and let Compose generate names. Other services should use the **service name** `web` for discovery, never the container name.

### 5.6 Testing DNS Round Robin

```bash
docker compose up -d --scale web=3
docker compose run --rm --no-deps --entrypoint sh web -c 'getent hosts web'
```

```text
172.20.0.3      web
172.20.0.4      web
172.20.0.5      web
```

Compose creates a one-off `run` container on the same network, so the lookup hits the embedded DNS server. A client calling `web` may get any of the addresses first. Many HTTP clients and connection pools resolve once and then reuse the connection, so traffic can still skew toward one replica.

### 5.7 Reverse Proxy With Re-Resolution (nginx)

```yaml
services:
  proxy:
    image: nginx:1.27-alpine
    ports: ["8080:80"]
    volumes: ["./nginx.conf:/etc/nginx/nginx.conf:ro"]
    depends_on:
      web: { condition: service_healthy }
  web:
    image: nginxdemos/hello:plain-text
    expose: ["80"]
    scale: 3
```

```nginx
# nginx.conf (fragment)
events {}
http {
  resolver 127.0.0.11 valid=5s ipv6=off;   # Docker embedded DNS
  server {
    listen 80;
    location / {
      set $upstream http://web:80;          # variable forces runtime resolution
      proxy_pass $upstream;
    }
  }
}
```

```bash
docker compose up -d
for i in 1 2 3 4 5 6; do curl -s localhost:8080 | grep 'Server address'; done
```

```text
Server address: 172.20.0.3:80
Server address: 172.20.0.4:80
Server address: 172.20.0.5:80
...
```

A plain `proxy_pass http://web;` resolves the name **once at startup** and pins those IPs; after you scale or a replica restarts with a new IP, nginx keeps the stale address. The `resolver` plus variable pattern forces periodic re-resolution.

### 5.8 Dynamic Discovery With Traefik

```yaml
services:
  traefik:
    image: traefik:v3.1
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
    ports: ["8080:80"]
    volumes: ["/var/run/docker.sock:/var/run/docker.sock:ro"]
  web:
    image: nginxdemos/hello:plain-text
    labels:
      - traefik.enable=true
      - traefik.http.routers.web.rule=PathPrefix(`/`)
      - traefik.http.services.web.loadbalancer.server.port=80
    scale: 3
```

Traefik watches Docker events and updates its backend list as replicas appear, disappear or fail health checks. No restart or config reload is needed when you run `--scale web=6`. Note that mounting the Docker socket gives the proxy broad control over the host (see section 7).

### 5.9 Per-Replica Inspection and Rolling Restarts

```bash
docker compose ps --all
docker compose logs --index 2 web          # logs for web-2 only
docker compose exec --index 3 web sh       # shell in web-3
docker compose port --index 2 web 80       # host mapping of replica 2 (if published)
docker compose restart web                 # restarts all replicas at once (not rolling)
```

### 5.10 What Compose Ignores From `deploy`

```yaml
deploy:
  replicas: 3                    # honored
  resources: { limits: {...} }   # honored (per replica)
  restart_policy: {...}          # honored
  update_config:                 # IGNORED by docker compose (Swarm-only semantics)
    parallelism: 1
    order: start-first
  placement: {...}               # IGNORED
```

Compose accepts the whole `deploy` block for compatibility with Swarm files, but only a subset has effect on a single host. Check what applies with `docker compose config` and your engine's behavior rather than assuming parity with `docker stack deploy`.

## 6. Production Usage Notes

- **One proxy owns the host port;** replicas are internal (`expose` or no ports). This avoids port conflicts and gives you TLS termination, health-based routing and rate limiting in one place.
- **Health checks are mandatory for scaled services** ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)); the proxy or DNS layer must be able to drop a sick replica, and `depends_on: condition: service_healthy` should gate the proxy start.
- **Limits are per replica.** `limits.memory: 512M` with `scale: 4` can consume 2 GB. Size the host accordingly ([§89](../Part12/Section-89-Part12-Resource-Management-at-Scale.md)).
- **State stays outside replicas.** Use a database, cache or object store. Named volumes mounted into multiple replicas are shared (same data), which is only safe for read-mostly or properly locked data.
- **Sessions:** either stateless tokens or shared session store (Redis), or sticky routing at the proxy.
- **Logging** from N replicas interleaves; include the container name or index in log metadata ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md), [§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)).
- **Zero-downtime updates** need start-first behavior that Compose does not provide natively; see patterns in [§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md).
- **A single host is a single failure domain.** Scaling here improves concurrency and restart tolerance, not availability. For multi-host scale use Swarm ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)) or Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 7. Security Considerations

- **Replicas multiply exposure.** Every published port range or ephemeral port is a new listener; prefer `127.0.0.1:` binding for dev scale tests and a single proxy for real traffic.
- **Docker socket in a proxy** (Traefik, nginx-proxy) grants effective root on the host. Mount it read-only (which limits API writes only partly), place it behind a socket proxy that allows only `GET /containers`, `/events` and `/networks`, or use file-based provider configuration.
- **Shared volumes across replicas** share credentials and data; one compromised replica can alter files seen by all. Mount `:ro` wherever possible.
- **Secrets are mounted identically in every replica;** rotate them by recreating all replicas, and avoid per-replica secrets in environment variables ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Resource limits protect the host** from runaway replicas (memory leaks, fork bombs): set `memory`, `cpus` and `pids_limit` per replica ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)).
- **Network scope:** replicas share a network; segment databases onto an internal network so the proxy cannot reach them ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` when scaling | Fixed host port in `ports` | Port range, ephemeral port, or proxy-only publishing |
| Warning: `container_name` prevents scaling | Fixed name | Remove `container_name` |
| Only one replica receives traffic | Client or proxy resolved DNS once | Use proxy with `resolver`, Traefik, or re-resolving clients |
| Traffic to removed replica fails | Stale DNS or proxy cache | Short DNS TTL (`valid=5s`), health-checked upstreams |
| Scale resets to 1 after next `up` | `--scale` not repeated; file says 1 | Set `scale:` or `deploy.replicas`, or repeat `--scale` |
| Replicas corrupt a shared file | Concurrent writers to the same volume | Move state to a database, or lock/serialize |
| `up` conflict between `scale` and `deploy.replicas` | Both set to different values | Use one attribute |
| Host runs out of memory at `--scale 10` | Per-replica limits multiply | Lower limits, fewer replicas, bigger host |
| `update_config` has no effect | Swarm-only semantic | Use Swarm or an external rollout script |
| Healthy replicas flip on startup | Proxy starts before replicas are ready | `depends_on: service_healthy`, or `up --wait` |
| Sticky sessions break after scaling | In-memory session state | Shared session store or sticky routing |

## 9. Best Practices

- Design services stateless first; scaling is then a configuration change.
- Remove `container_name` and fixed host ports from any service that may be scaled.
- Publish only the proxy; keep replicas on internal networks.
- Declare health checks and gate dependents on `service_healthy`.
- Use one scale convention (`deploy.replicas` or `scale`) per project, and override per environment ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)).
- Set per-replica resource limits and compute the total against host capacity.
- Make the proxy re-resolve or discover replicas dynamically.
- Test scale up, scale down and a killed replica as part of CI smoke tests (`up --scale web=3 --wait`, then `kill` one).
- Document the single-host limitation and the path to an orchestrator.

## 10. Common Anti-Patterns / Mistakes

- Scaling a stateful service (a database, a message broker with local storage) by setting `--scale db=3` and expecting clustering.
- Publishing the same fixed host port on a scaled service.
- Trusting `deploy.update_config` or `placement` to work in Compose.
- Using a plain `proxy_pass http://web;` and assuming it follows scale changes.
- Relying on the container name (`shop-web-1`) in application config instead of the service name.
- Using Compose scaling as a high-availability strategy on a single VM.
- Writing logs or uploads to local container filesystems per replica and expecting them to be unified.
- Forgetting that `--scale` is not persisted and must be repeated or encoded in the file.
- Mounting the Docker socket read-write into a public-facing proxy.

## 11. Interview Questions

**🎯 Beginner:** _"How do you run three instances of a `web` service with Docker Compose, and what are the containers called?"_
**Model answer:** Run `docker compose up -d --scale web=3`, or set `deploy.replicas: 3` or `scale: 3` on the service. Compose names them `<project>-web-1`, `-2` and `-3`, and they all join the project network, where the service name `web` resolves to all three IPs. The service must not set `container_name`, and it must not publish a single fixed host port, because those cannot be duplicated.
_What the interviewer is probing for:_ Knowing the three ways to set replicas, naming, and the uniqueness constraints.

**🎯 Intermediate:** _"You scale a service to 3 and get `port is already allocated`. Explain and give two fixes."_
**Model answer:** `ports: "8080:80"` binds host port 8080, and only one container can own it, so the second replica fails. Fix one: publish a range (`8080-8082:80`) or an ephemeral port (`"80"`) and look it up with `docker compose port --index N`. Fix two, the better one: do not publish the replicated service at all, and put a reverse proxy (nginx, Traefik, HAProxy) on the same network that publishes one host port and forwards to `web` via the Docker DNS name. This also centralizes TLS and health-based routing.
_What the interviewer is probing for:_ Understanding port publishing as a host-level exclusive resource and the proxy pattern.

**🎯 Senior:** _"After `--scale web=6`, nginx still sends everything to the original three containers. Why, and how do you fix it without restarting nginx every time?"_
**Model answer:** With `proxy_pass http://web;` nginx resolves the hostname once at startup (or config reload) and caches the IPs for the life of the worker. New replicas are invisible, and removed ones return errors. Docker's embedded DNS at 127.0.0.11 does return all current addresses, so the fix is to make nginx query it at runtime: set `resolver 127.0.0.11 valid=5s;` and use a variable (`set $upstream http://web:80; proxy_pass $upstream;`). Alternatives: Traefik with the Docker provider, which subscribes to engine events, or HAProxy with `server-template` and DNS resolution. Add health checks so failed replicas leave rotation.
_What the interviewer is probing for:_ DNS caching in proxies, embedded DNS behavior, and dynamic discovery options.

**🎯 Architect:** _"A team wants to run its 12-service stack on one VM with Compose and calls it 'highly available' because each service has 3 replicas. Evaluate and propose a path."_
**Model answer:** Replicas on one host protect against a process crash or a bad restart, and give concurrency, but the VM, its disk, its network and the Docker daemon remain a single failure domain, so it is not high availability. Also `deploy.update_config`, placement and rolling updates are not enforced by Compose, so deploys are not zero-downtime without scripted start-first logic. I would keep Compose for dev, CI and small single-node deployments with a proxy, health checks, resource limits and external state, and state the availability target honestly. For real HA, move the same images to Swarm (smallest step, reuses Compose-style files with `docker stack deploy`) or Kubernetes (rolling updates, PodDisruptionBudgets, multi-zone scheduling, managed state), with databases on managed services. Keep the application stateless and 12-factor so the migration is only a packaging change.
_What the interviewer is probing for:_ Distinguishing scalability from availability, knowing Compose's limits, and giving a pragmatic migration path.

## 12. Common Misconceptions

- "`--scale` load-balances traffic." It only creates containers; DNS round robin or a proxy distributes traffic.
- "Compose performs rolling updates for replicas." `update_config` is ignored; `up` recreates changed replicas without Swarm semantics.
- "`deploy:` works exactly like in Swarm." Only a subset (replicas, resources, restart policy, labels) applies.
- "Replicas have separate volumes by default." A named volume is shared by all replicas of the service.
- "Scale persists across runs." The CLI flag does not; the file's value does.
- "Scaling `db` gives a replicated database." You get N independent processes (often fighting over one volume).

## 13. 🔑 Key Takeaways

- Replica count: `deploy.replicas` or `scale` in the file; `--scale` on `up` overrides.
- Containers are named `<project>-<service>-<n>` and share the service DNS name.
- No `container_name` and no fixed host ports on scaled services; publish through a proxy.
- Proxies must re-resolve DNS or use dynamic discovery to follow scale changes.
- Limits apply per replica and multiply across the host.
- Compose ignores Swarm-only `deploy` options such as `update_config` and `placement`.
- Single-host scaling gives concurrency, not high availability.

## 14. Related Concepts & What's Next

Related: services and networks ([§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), dependency ordering and health ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), environment-specific replica counts ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)), DNS and service discovery ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)), resource constraints ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)), zero-downtime patterns ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)), Swarm ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)). Next, [§40](Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md) takes a systematic tour of the Compose CLI commands used throughout this part, including per-replica targeting with `--index`.

**Next Section:** [§40](Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md) — `Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md`
