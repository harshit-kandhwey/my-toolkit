# Section 35 (Part 5): Services, Networks, and Volumes in docker-compose.yml

## 1. Definition

**Plain language:** A Compose file is built from three kinds of things. A **service** is a description of one container (and how many copies of it to run). A **network** is a private virtual switch the containers plug into. A **volume** is storage that outlives any one container. Services reference networks and volumes by name, and Compose creates all three together.

**Precise definition:**

- **`services`** (required): a map of service name to configuration. Each service becomes one or more containers built from an `image:` or a `build:` section. The service name is also the container's DNS name on the project networks.
- **`networks`** (top level): named networks created with a driver (default `bridge` on a single host). If you declare none, Compose creates one network called `<project>_default`, attaches every service to it, and enables name-based discovery ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)).
- **`volumes`** (top level): named volumes created via a volume driver (default `local`). Service-level `volumes:` entries then mount a named volume, a host path (bind mount), or a `tmpfs` ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)).

Resources are named `<project>_<name>` (for example `demo_default`, `demo_pgdata`) unless the resource sets `name:` or is `external: true`.

> 💡 **Tip:** The top-level `networks:` and `volumes:` blocks declare resources; the per-service `networks:` and `volumes:` keys use them. A service that mentions a name not declared at the top level (other than a bind-mount path) fails validation.

## 2. Why This Matters

- These three blocks are 90 percent of every real Compose file. Mistakes here cause the classic failures: containers that cannot reach each other, data lost on `down -v`, or ports exposed to the world.
- Understanding network scoping gives free segmentation: a database that is only on a `backend` network is unreachable from the edge proxy ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- The distinction between named volumes and bind mounts determines portability, permissions and performance ([§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md)).
- Service keys map one-to-one onto `docker run` flags, so reading them fluently makes the earlier CLI knowledge reusable.

## 3. Prerequisites and Dependencies

You need the file format basics from [§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), `docker run` flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), user-defined bridge networks and their DNS ([§43](../Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)), port publishing ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)), and named volume lifecycle ([§52](../Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)). Health checks and restart policies ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)) and resource limits ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) appear as service keys.

## 4. Architecture / Conceptual Diagram

```text
 project "shop"
 ┌────────────────────────────────────────────────────────────────────────┐
 │                                                                        │
 │  host :8080 ──► ┌───────┐                                              │
 │  (ports)        │ proxy │                                              │
 │                 └───┬───┘                                              │
 │     network "frontend" (shop_frontend)                                 │
 │       ───────────────┼────────────────                                 │
 │                  ┌───┴───┐                                             │
 │                  │  api  │ ◄── env, healthcheck, restart               │
 │                  └───┬───┘                                             │
 │     network "backend" (shop_backend, internal: true)                   │
 │       ───────────────┼───────────────                                  │
 │                  ┌───┴───┐        ┌─────────┐                          │
 │                  │  db   │ ◄───── │ pgdata  │  named volume            │
 │                  └───────┘        │ (shop_pgdata)                      │
 │                                   └─────────┘                          │
 │      ./init.sql ──► db:/docker-entrypoint-initdb.d  (bind mount, ro)   │
 └────────────────────────────────────────────────────────────────────────┘

  DNS: "api" resolves to the api container IP on frontend;
       "db" resolves only for services attached to backend.
```

- **Service name = DNS name**, per network. The proxy cannot resolve `db` because they share no network.
- **`internal: true`** gives the network no gateway to the outside, so `db` has no outbound internet.
- **Volumes survive** `docker compose down`; they are removed only with `down -v` (or `volume rm`).

## 5. Hands-On

### 5.1 A Complete Three-Tier Example

```yaml
name: shop

services:
  proxy:
    image: nginx:1.27-alpine
    ports:
      - "127.0.0.1:8080:80"
    volumes:
      - ./proxy/default.conf:/etc/nginx/conf.d/default.conf:ro
    networks: [frontend]
    depends_on:
      api:
        condition: service_healthy

  api:
    build:
      context: ./api
      dockerfile: Dockerfile
      args:
        APP_VERSION: "1.4.2"
    environment:
      DB_HOST: db
      DB_NAME: shop
    networks: [frontend, backend]
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/healthz"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      POSTGRES_DB: shop
    secrets: [db_password]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks: [backend]
    restart: unless-stopped

networks:
  frontend:
  backend:
    internal: true

volumes:
  pgdata:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

```bash
docker compose up -d --build
docker compose ps
docker network ls --filter label=com.docker.compose.project=shop
docker volume ls  --filter label=com.docker.compose.project=shop
```

```text
NETWORK ID     NAME            DRIVER    SCOPE
a1b2c3d4e5f6   shop_backend    bridge    local
0f9e8d7c6b5a   shop_frontend   bridge    local
DRIVER    VOLUME NAME
local     shop_pgdata
```

### 5.2 Service Keys That Map to `docker run`

| Compose key | `docker run` equivalent |
|---|---|
| `image` / `build` | image argument / `docker build` |
| `command` / `entrypoint` | args after image / `--entrypoint` ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) |
| `environment` / `env_file` | `-e` / `--env-file` ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)) |
| `ports` | `-p` |
| `expose` | metadata only, like `EXPOSE` ([§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)) |
| `volumes` | `-v` / `--mount` |
| `networks` | `--network` |
| `restart` | `--restart` |
| `healthcheck` | `--health-cmd` and related |
| `user`, `working_dir` | `-u`, `-w` |
| `read_only`, `tmpfs` | `--read-only`, `--tmpfs` ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)) |
| `cap_add`, `cap_drop`, `security_opt` | `--cap-add`, `--cap-drop`, `--security-opt` |
| `mem_limit`, `cpus`, `pids_limit` or `deploy.resources.limits` | `--memory`, `--cpus`, `--pids-limit` |
| `init: true` | `--init` |
| `stop_signal`, `stop_grace_period` | `--stop-signal`, `--stop-timeout` |

### 5.3 `build:` in Detail

```yaml
services:
  api:
    image: registry.example.com/shop/api:1.4.2   # tag applied to the built image
    build:
      context: ./api
      dockerfile: Dockerfile.prod
      target: runtime          # multi-stage target
      args:
        APP_VERSION: "1.4.2"
      cache_from:
        - registry.example.com/shop/api:cache
      platforms:
        - linux/amd64
        - linux/arm64
```

`docker compose build` and `up --build` use BuildKit. If both `image:` and `build:` are present, the built image is tagged with the `image:` name, so `docker compose push` publishes it ([§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)).

### 5.4 Networks: Default, Custom, Aliases, External

```yaml
services:
  api:
    networks:
      backend:
        aliases: [api.internal, backend-api]
        ipv4_address: 172.28.0.10
  legacy:
    network_mode: "service:api"      # share api's network namespace

networks:
  backend:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
  shared:
    external: true                   # must already exist
    name: corp-shared-net
```

```bash
docker network create corp-shared-net
docker compose exec api getent hosts backend-api
```

```text
172.28.0.10     backend-api
```

Key points:

- With no `networks:` anywhere, every service joins `<project>_default`.
- Once a service lists `networks:`, it joins **only** those; the default network is no longer implicit (add `default` explicitly to keep it).
- `aliases` give extra DNS names for a service **on that network only**.
- `external: true` means Compose never creates or deletes it; `compose up` errors if it is missing. This is how stacks in different projects talk to each other.
- `internal: true` blocks traffic leaving the network. `attachable`, `driver_opts` and `labels` are also available. The `enable_ipv6` option turns on IPv6.
- `network_mode: host` / `none` / `service:<name>` / `container:<id>` bypass Compose-managed networks entirely and cannot be combined with `networks:`.

### 5.5 Ports: Publish vs Expose

```yaml
services:
  web:
    ports:
      - "8080:80"                 # host 8080 -> container 80, all interfaces
      - "127.0.0.1:9090:80"       # loopback only
      - "80"                      # random host port
      - "5353:53/udp"
    expose:
      - "3000"                    # reachable by other services only, not the host
```

Containers on the same Compose network reach each other on the **container port** directly (`http://api:3000`), so `ports:` is only needed for host or external access. Always quote values: YAML can read `22:22` as a base-60 number.

### 5.6 Volumes: Named, Bind and tmpfs

```yaml
services:
  app:
    volumes:
      - appdata:/var/lib/app                 # named volume (short)
      - ./config:/etc/app:ro                 # bind mount, read-only
      - type: volume                         # long syntax
        source: logs
        target: /var/log/app
        volume:
          nocopy: true
      - type: bind
        source: ./src
        target: /app/src
        bind:
          create_host_path: false            # error if source is missing
      - type: tmpfs
        target: /tmp
        tmpfs:
          size: 67108864                     # 64 MiB

volumes:
  appdata:
  logs:
    name: shared-logs                         # fixed name, not project-prefixed
  nfsdata:
    driver: local
    driver_opts:
      type: nfs
      o: "addr=10.0.0.20,nfsvers=4,rw"
      device: ":/exports/data"
  legacydb:
    external: true                            # created outside Compose
```

Rules worth memorizing:

- A source starting with `.`, `/` or `~` is a **bind mount**; a bare name is a **named volume** and must be declared at the top level.
- A new, empty named volume is **initialized from the image's content** at the mount path (copy-up). Bind mounts hide the image content instead. `nocopy` disables copy-up.
- With the short syntax, a missing bind source is created as a root-owned directory; with the long syntax and `create_host_path: false` it errors, which is safer.
- Named volumes persist across `down`. Only `docker compose down -v` (or `docker volume rm`) deletes them; `external: true` volumes are never deleted by Compose.
- `volumes_from` is legacy; prefer sharing a named volume.

### 5.7 Verifying Wiring

```bash
docker compose config --format json | jq '.services.api.networks'
docker compose exec api sh -c 'getent hosts db'        # works if api shares a network with db
docker compose exec proxy sh -c 'getent hosts db'      # empty: different networks
docker compose volumes
docker volume inspect shop_pgdata --format '{{.Mountpoint}} {{.Labels}}'
```

```text
{"backend":null,"frontend":null}
172.19.0.2      db
(no output)
DRIVER    VOLUME NAME
local     shop_pgdata
/var/lib/docker/volumes/shop_pgdata/_data map[com.docker.compose.project:shop com.docker.compose.version:2.29.7 com.docker.compose.volume:pgdata]
```

### 5.8 Resource Limits and Hardening on a Service

```yaml
services:
  api:
    image: ghcr.io/example/api:1.4.2
    user: "10001:10001"
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    init: true
    stop_grace_period: 30s
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
          pids: 200
      replicas: 2
```

Compose v2 honors `deploy.resources.limits` and `deploy.replicas` outside Swarm. The older `mem_limit` and `cpus` service-level keys remain supported; avoid setting both for the same resource.

## 6. Production Usage Notes

- **Default network is enough for tiny stacks**; add explicit networks when you want segmentation (`frontend`, `backend`, `internal: true` for databases).
- **Do not publish database ports** in production. Only the edge service should have `ports:`; others use the internal network.
- **Name important volumes** with `name:` and consider `external: true` so an accidental `down -v` cannot remove production data.
- **Restart policy** (`unless-stopped`) plus a `healthcheck` forms the minimum self-recovery set ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)). Compose does not restart unhealthy containers by itself; `restart` only reacts to exits.
- **Do not set `container_name`** for services you may scale ([§39](Section-39-Part5-Scaling-Services-with-Compose.md)); a fixed name allows only one container.
- **Logging:** set `logging.driver` and rotation options per service ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)).
- **Bind mounts in production** tie the deployment to host paths and UID/GID layout; prefer named volumes or volume drivers ([§53](../Part7/Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md)).
- **Backups:** volumes are not backed up by Compose; use the strategies in [§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md).
- **Ordering** of startup is a separate concern ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)).

## 7. Security Considerations

- **Bind to loopback** (`127.0.0.1:8080:80`) for anything not meant to be public. Docker's published ports bypass typical host firewall rules on Linux because Docker manages its own iptables/nftables chains ([§45](../Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)).
- **Segment networks**: put databases on an `internal: true` network so a compromised front-end container cannot reach the internet from the database tier, and so the proxy has no route to the database at all ([§49](../Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)).
- **Mount read-only** (`:ro` or `read_only: true`) wherever the app does not write. Mounting the Docker socket (`/var/run/docker.sock`) gives root-equivalent control of the host ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)).
- **Harden services**: non-root `user`, `cap_drop: [ALL]` plus only the needed `cap_add`, `no-new-privileges`, and a `read_only` root filesystem with `tmpfs` for scratch paths ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).
- **Secrets:** use top-level `secrets:` (mounted at `/run/secrets/<name>`) instead of `environment:` values, which show up in `docker inspect` ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **Bind-mount host paths** expose the host filesystem to the container; never mount a home directory, `/`, or cloud-sync folders.
- `privileged: true`, `network_mode: host` and `pid: host` remove most isolation; require justification in review.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `could not resolve host: db` | Services on different networks, or `db` not on the caller's network | Put both on a shared network; verify with `config` |
| App connects to `localhost:5432` and fails | `localhost` is the container itself | Use the service name (`db`) |
| `port is already allocated` | Host port in use by another process or project | Change the host side or stop the other stack |
| Service reachable from other containers but not host | Only `expose:`, no `ports:` | Add a `ports:` mapping |
| Host can reach port but others cannot | Bound to `127.0.0.1` and accessed from another machine | Bind to `0.0.0.0` deliberately, or front with a proxy |
| Data gone after restart | Anonymous volume or `down -v` | Use a named volume; avoid `-v` on `down` |
| `permission denied` writing to bind mount | Host directory owned by another UID | Match `user:` to owner, or `chown` the host directory |
| Empty directory where files expected | Bind mount hid the image's content | Use a named volume or copy files at build |
| `network x declared as external, but could not be found` | External network missing | `docker network create x` first |
| `service refers to undefined volume` | Named volume not declared at top level | Add to `volumes:` |
| Duplicate subnet / `Pool overlaps` | Custom `ipam` conflicts with existing network | Choose a free subnet |
| Cannot scale: name already in use | `container_name:` set | Remove it |

## 9. Best Practices

- One process concern per service; scale or replace services rather than packing daemons together.
- Reference other services by service name and container port.
- Publish only what must be reachable, with explicit host IPs.
- Declare networks and volumes explicitly with meaningful names, even when defaults would work.
- Use long syntax for mounts you care about (`bind.create_host_path`, `read_only`).
- Prefer named volumes for state; bind mounts for source code in development ([§41](Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md)).
- Add `healthcheck`, `restart`, `init: true`, and resource limits to every long-running service.
- Pin image versions; build once and tag, rather than rebuilding on every host.
- Verify with `docker compose config` and `docker compose ps` after every structural change.

## 10. Common Anti-Patterns / Mistakes

- Publishing the database port (`5432:5432`) "for convenience" on a shared or internet-facing host.
- Using `links:` or `depends_on` as a substitute for networking knowledge.
- Using `container_name:` and `hostname:` everywhere, blocking scaling and causing collisions.
- Mounting `.:/app` over an image's installed dependencies (hides `node_modules`) without an anonymous or named volume to mask it.
- Relying on anonymous volumes (`- /var/lib/data`) and losing track of them.
- Setting `network_mode: host` to "fix" a connectivity problem instead of diagnosing it ([§47](../Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)).
- Running `docker compose down -v` in a script against a production project.
- Hard-coding IP addresses between services instead of using DNS names.
- Putting every service on one flat network regardless of trust level.

## 11. Interview Questions

**🎯 Beginner:** _"In a Compose file, how does the `web` service reach the `db` service, and what is the difference between `ports` and `expose`?"_
**Model answer:** Compose creates a default bridge network per project and attaches every service to it; the embedded DNS server resolves each service name to the container IP, so `web` connects to `db:5432` using the container port. `ports:` publishes a container port on the host (`HOST:CONTAINER`) so the outside world can reach it. `expose:` is documentation/metadata that makes a port known to other containers but does not publish it; on a shared network containers can reach each other's ports even without it.
_What the interviewer is probing for:_ Service-name DNS and the difference between host publishing and internal reachability.

**🎯 Intermediate:** _"A teammate runs `docker compose down -v` and the database is empty on the next `up`. Explain why, and how would you protect against it?"_
**Model answer:** The `-v` flag removes named volumes declared in the Compose file, including the one holding the Postgres data directory. Without `-v`, `down` removes containers and networks but keeps volumes. To protect: mark the production volume `external: true` (Compose never deletes external volumes) or give it a fixed `name:` and restrict who can run destructive commands; keep tested backups ([§55](../Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)); and avoid putting `-v` into scripts that target persistent environments. In development, `-v` is a convenient reset.
_What the interviewer is probing for:_ Volume lifecycle, destructive flags, and defensive design.

**🎯 Senior:** _"Design the networking for a Compose stack with a reverse proxy, an API, a worker, Postgres and Redis so that a compromised proxy cannot reach the database, and the database cannot reach the internet."_
**Model answer:** Create two networks: `frontend` (proxy and api) and `backend` with `internal: true` (api, worker, Postgres, Redis). Only the proxy publishes a port, bound explicitly. The API sits on both networks and is the only bridge; DNS names resolve per network, so the proxy cannot even resolve `db`. The internal flag removes the gateway, so the data tier has no outbound route; if the worker needs internet it joins a third non-internal `egress` network. Add `cap_drop: [ALL]`, non-root users, and read-only roots, with secrets via `secrets:`. Verify with `getent hosts` and `curl` from each container, and test negative paths. Note that network segmentation here is L3/L4 separation on a single host, not a policy engine.
_What the interviewer is probing for:_ Applying segmentation, internal networks and least privilege, and verifying negatives.

**🎯 Architect:** _"When should a Compose project use external networks and volumes, and what operational risks does that introduce?"_
**Model answer:** Use `external: true` when a resource has a lifecycle independent of the stack: shared networks that several projects (a proxy project and app projects) join, or production data volumes that must survive redeploys and accidental `down -v`. Benefits: decoupling, safer data handling, cross-project communication. Risks: out-of-band creation steps (the stack fails if the resource is missing, so provisioning must be part of the runbook or IaC), configuration drift because Compose no longer owns driver options or subnets, name collisions between teams on one daemon, and wider blast radius since many projects share one network. Mitigate with naming conventions, provisioning in automation, health checks that detect absence, and documented ownership. At larger scale, this is where an orchestrator with first-class network and storage objects becomes preferable.
_What the interviewer is probing for:_ Lifecycle ownership trade-offs and operational thinking beyond YAML syntax.

## 12. Common Misconceptions

- "`depends_on` creates the network link." Networking is automatic; `depends_on` only affects start order ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)).
- "`expose` publishes a port." It does not; use `ports`.
- "Services need `links:` to find each other." Shared network plus service name suffices.
- "`localhost` in one container reaches another service." It is the container's own loopback.
- "Volumes are deleted on `docker compose down`." Only with `-v`.
- "Listing `networks:` on a service adds to the default network." It replaces implicit default membership.
- "Bind mounts and named volumes behave the same." Initialization, ownership, portability and performance differ.
- "`internal: true` blocks traffic between containers." It blocks traffic to and from outside the network; containers on it still talk to each other.

## 13. 🔑 Key Takeaways

- Services = containers; networks = private L2 domains with DNS; volumes = persistent storage.
- Service name is the hostname; use container ports between services.
- `ports` publishes to the host, `expose` is metadata; bind to loopback when possible.
- Declare top-level networks and volumes; `external: true` means Compose never creates or deletes.
- Named volumes survive `down`; `down -v` deletes them.
- Use internal networks, read-only mounts, secrets and dropped capabilities for defense in depth.
- Avoid `container_name` if you intend to scale.

## 14. Related Concepts & What's Next

Related: file format and merge rules ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), network drivers ([§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)), service discovery ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)), communication patterns ([§48](../Part6/Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md)), and persistence patterns ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)). Next, [§36](Section-36-Part5-Environment-Variables-and-env-Files.md) covers how environment variables, `.env` files and interpolation feed configuration into these services.

**Next Section:** [§36](Section-36-Part5-Environment-Variables-and-env-Files.md) — `Section-36-Part5-Environment-Variables-and-env-Files.md`
