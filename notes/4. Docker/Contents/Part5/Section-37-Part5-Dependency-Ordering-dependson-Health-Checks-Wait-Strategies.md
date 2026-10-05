# Section 37 (Part 5): Dependency Ordering: depends_on, Health Checks, Wait Strategies

## 1. Definition

**Plain language:** In a multi-container app the web service needs the database, but "the database container has started" is not the same as "the database is ready for queries." Compose gives you `depends_on` to control *start order*, and health checks to define *readiness*. Combining the two is how you make `docker compose up` start things in a sensible, reliable order.

**Precise definition:** `depends_on` expresses start-up and shutdown ordering between services. It has two syntaxes:

- **Short syntax:** a list of service names. Compose starts dependencies first, but only waits until their containers are *started* (equivalent to `condition: service_started`).
- **Long syntax:** a map per dependency with `condition`, plus optional `restart` and `required`.

| `condition` | Waits until the dependency is... |
|---|---|
| `service_started` (default) | created and running (process launched) |
| `service_healthy` | reporting `healthy` per its `healthcheck` |
| `service_completed_successfully` | finished and exited with code 0 (one-shot jobs) |

Long-syntax extras: `restart: true` restarts the dependent when the dependency is restarted by an explicit Compose operation (Compose 2.17+); `required: false` makes Compose only warn, rather than fail, if the dependency is missing or not started (2.20+, useful with profiles). Shutdown runs in reverse dependency order.

> 💡 **Tip:** `depends_on` with the default condition guarantees *order*, never *readiness*. For readiness, pair `condition: service_healthy` with a real `healthcheck` on the dependency.

## 2. Why This Matters

- Apps that connect to a database at boot crash-loop when the database is still initializing, even though its container is "up."
- Race conditions that pass on a fast laptop and fail on a slow CI runner are almost always missing readiness gates.
- One-time setup (schema migrations, seed data) needs "run to completion, then start the app" semantics, which `service_completed_successfully` provides.
- Correct shutdown order prevents data loss (the app stops before the database it writes to).
- Interviewers often ask whether `depends_on` waits for a database; the answer separates people who have read the docs from people who have only copied snippets.

## 3. Prerequisites and Dependencies

Requires Compose file structure ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), services and networks ([§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), and the engine-level `HEALTHCHECK` and restart policy model ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)). Variables used in the examples come from [§36](Section-36-Part5-Environment-Variables-and-env-Files.md). Container states and exit codes are in the lifecycle section ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)). Profiles interact with dependencies and are covered in [§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md).

## 4. Architecture / Conceptual Diagram

```text
  compose.yaml                         docker compose up
  ┌───────────┐                        order of operations
  │ migrate   │ completed_successfully
  │ web       │──────────────────┐
  │ db        │ service_healthy  │
  └───────────┘                  ▼

   t0   db      created ─► started ─► [health: starting] ─► healthy
                                          (start_period)       │
   t1                                                          ▼
        migrate                          created ─► started ─► exit 0
                                                                │
   t2                                                           ▼
        web                                           created ─► started

   Shutdown (docker compose down): web ─► (migrate already gone) ─► db
   Reverse of the dependency graph.

  Health states of a container with a healthcheck:
    starting ──(test passes)──► healthy
    starting ──(retries failures AFTER start_period)──► unhealthy
    healthy  ──(retries consecutive failures)──► unhealthy
```

- **Start order** comes from the dependency graph; independent services start in parallel.
- **Readiness** comes only from health checks (or completion for jobs).
- **Failure propagation:** if a `service_healthy` dependency turns `unhealthy`, or a `service_completed_successfully` dependency exits non-zero, `docker compose up` aborts with a "dependency failed to start" error.

## 5. Hands-On

### 5.1 Short Syntax: Order Only

```yaml
services:
  web:
    image: nginx:1.27-alpine
    depends_on:
      - api
  api:
    image: nginx:1.27-alpine
```

```bash
docker compose up -d
```

```text
 ✔ Container demo-api-1  Started
 ✔ Container demo-web-1  Started
```

`api` is started first, but `web` does not wait for `api` to be able to serve requests.

### 5.2 Health Check Plus `service_healthy`

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:?set DB_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d postgres"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 20s
  app:
    image: myapp:dev
    depends_on:
      db:
        condition: service_healthy
```

```bash
docker compose up -d
docker compose ps
```

```text
NAME         IMAGE       SERVICE   STATUS                    PORTS
demo-db-1    postgres:16 db        Up 18 seconds (healthy)   5432/tcp
demo-app-1   myapp:dev   app       Up 3 seconds
```

`app` was created only after `db` reported `healthy`.

### 5.3 Health Check Fields

| Field | Meaning | Default |
|---|---|---|
| `test` | `["CMD", ...]` exec form, `["CMD-SHELL", "..."]` via `/bin/sh -c`, `["NONE"]` disables an inherited check | none |
| `interval` | Time between checks | 30s |
| `timeout` | A single check fails if it runs longer | 30s |
| `retries` | Consecutive failures to flip to `unhealthy` | 3 |
| `start_period` | Grace period; failures here do not count toward `retries`, but a success marks healthy at once | 0s |
| `start_interval` | Check frequency during `start_period` (Engine 25+) | 5s |

Common probes (the binary must exist in the image):

```yaml
# MySQL / MariaDB
test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "--silent"]
# Redis
test: ["CMD", "redis-cli", "ping"]
# HTTP service (curl present)
test: ["CMD-SHELL", "curl -fsS http://localhost:8080/healthz || exit 1"]
# HTTP service on a slim image (BusyBox wget)
test: ["CMD-SHELL", "wget -q --spider http://localhost:8080/healthz || exit 1"]
```

### 5.4 One-Shot Job: `service_completed_successfully`

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:?set DB_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 10
  migrate:
    image: myapp:dev
    command: ["./manage", "migrate"]
    depends_on:
      db:
        condition: service_healthy
    restart: "no"
  app:
    image: myapp:dev
    depends_on:
      migrate:
        condition: service_completed_successfully
```

Chain: `db` healthy, then `migrate` runs and exits 0, then `app` starts. If `migrate` exits 1:

```text
dependency failed to start: container demo-migrate-1 exited (1)
```

### 5.5 Blocking `up` Until Everything Is Ready

```bash
docker compose up -d --wait
docker compose up -d --wait --wait-timeout 120
echo $?
```

```text
 ✔ Container demo-db-1   Healthy
 ✔ Container demo-app-1  Healthy
0
```

`--wait` returns after all services are running and, where defined, healthy. It exits non-zero on failure or timeout, which is ideal for CI scripts that run tests right after `up`.

### 5.6 Application-Level Retry (the Robust Alternative)

Health gates only protect first start. If the database restarts later, the app must reconnect. A retry loop in the app or its entrypoint covers both:

```sh
#!/bin/sh
# docker-entrypoint.sh: last-resort wait for a TCP dependency
set -e
host="${DB_HOST:-db}"; port="${DB_PORT:-5432}"
i=0
until nc -z "$host" "$port" 2>/dev/null; do
  i=$((i+1)); [ "$i" -ge 60 ] && { echo "db not reachable"; exit 1; }
  echo "waiting for $host:$port ($i/60)"; sleep 1
done
exec "$@"
```

A TCP port being open still does not prove the database accepts logins; prefer a protocol-aware probe (`pg_isready`) or retries inside the client library. Third-party helpers (`wait-for-it.sh`, `dockerize -wait`) exist but are legacy when `service_healthy` is available.

### 5.7 Inspecting Health

```bash
docker inspect --format '{{json .State.Health}}' demo-db-1 | head -c 400
docker compose ps --format 'table {{.Service}}\t{{.Status}}'
docker compose events --json | head
```

```text
{"Status":"healthy","FailingStreak":0,"Log":[{"Start":"2026-10-06T10:00:05Z","End":"2026-10-06T10:00:05Z","ExitCode":0,"Output":"/var/run/postgresql:5432 - accepting connections\n"}]}
```

### 5.8 Optional and Restart-Aware Dependencies

```yaml
services:
  app:
    image: myapp:dev
    depends_on:
      db:
        condition: service_healthy
        restart: true        # restart app when db is restarted via Compose
      metrics:
        condition: service_started
        required: false      # warn, do not fail, if metrics is absent or in an inactive profile
  metrics:
    image: prom/prometheus:latest
    profiles: ["observability"]
```

## 6. Production Usage Notes

- **Single-host Compose in production** benefits from health gates plus `restart: unless-stopped` ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)); `depends_on` only matters at `up` time, not for runtime recovery.
- **Plain Docker never restarts an unhealthy container.** A `healthy`/`unhealthy` status is information for `depends_on`, `--wait` and external monitors; self-healing needs an orchestrator or an autoheal sidecar ([§88](../Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)).
- **Make checks cheap and local.** Probe from inside the container with the binary already in the image; do not add `curl` to a minimal image just for a check if the app can offer a `--healthcheck` subcommand.
- **Tune `start_period`** to real initialization time (first-boot database init, JVM warm-up) so slow starts are not marked unhealthy.
- **Separate liveness from readiness in your head.** Compose has one health signal; keep the check meaning "ready to serve," and keep it shallow (do not make web health fail when an optional downstream is down).
- **Use `up --wait` in CI** instead of arbitrary `sleep 10`.
- **Migrations as a job service** keep application images free of "run migrations at boot" races when you scale replicas ([§39](Section-39-Part5-Scaling-Services-with-Compose.md)).
- **Don't rely on ordering for correctness.** Treat it as an optimization; the application must tolerate dependency restarts.

## 7. Security Considerations

- **Health check commands run inside the container** with its privileges; avoid passing credentials on the command line (they show in `docker inspect`). Use `PGPASSFILE`, socket auth, or checks that need no password (`pg_isready`).
- **Do not expose health endpoints publicly** just to satisfy a check; probe `localhost` inside the container.
- **Verbose check output** is stored in the container's health log and may leak details; keep output short and non-sensitive.
- **Wait scripts that install tools at startup** (`apt-get install netcat`) enlarge attack surface and add network dependency; bake needed tools into the image or use an existing client.
- **Migration job containers** often hold elevated database credentials; give them a separate, tightly scoped secret and do not reuse them in the long-running service ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| App crashes at boot with "connection refused" | Short `depends_on` only orders start | Add `healthcheck` on dependency and `condition: service_healthy` |
| `service "app" depends on undefined service "db"` / dependency missing from active profiles | Typo or dependency in an inactive profile | Fix the name, enable the profile, or use `required: false` |
| `dependency failed to start: container x is unhealthy` | Check keeps failing | `docker inspect` `.State.Health.Log`, run the test command via `docker exec`, adjust `start_period` |
| Health stays `starting` forever | `interval` huge, or the probe hangs | Lower `interval`/`timeout`; ensure the command exits |
| Check always fails: `executable file not found` | `curl`/`pg_isready` not in the image | Use a tool that exists (BusyBox `wget`) or add it |
| `CMD-SHELL` check passes though the app is down | Command ends with `|| true` or tests the wrong port | Return a non-zero code on failure; probe the right endpoint |
| Dependent not restarted after db restart | `depends_on` is not runtime supervision | Use `restart: true` for Compose-driven restarts, plus client reconnect logic |
| `migrate` re-runs on every `up` | One-shot service is recreated or restarted | Set `restart: "no"`; make migrations idempotent |
| Cycle error: `dependency cycle detected` | A depends on B and B on A | Break the loop; introduce a third service or remove an edge |
| `--wait` hangs | A service has no healthcheck but exits, or never becomes healthy | Add `--wait-timeout`; check each service's state with `docker compose ps -a` |

## 9. Best Practices

- Give every service others depend on a real `healthcheck`, and use `condition: service_healthy`.
- Use `service_completed_successfully` for migrations and seed jobs, with `restart: "no"`.
- Keep checks fast (a few seconds), local, and dependency-free.
- Set `start_period` generously and `retries` modestly rather than a very long `interval`.
- Still write clients with connection retry and backoff ([§88](../Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)).
- Use `docker compose up --wait` in scripts and CI.
- Keep the dependency graph shallow and acyclic; document it in the Compose file with comments.
- Prefer protocol-aware probes over bare TCP checks.

## 10. Common Anti-Patterns / Mistakes

- Believing `depends_on: [db]` waits for the database to accept connections.
- Using `sleep 30` in a command or entrypoint to "wait for the db."
- A health check that always passes (`exit 0`) or only checks that the process exists.
- Putting credentials on the health check command line.
- Running migrations inside the app entrypoint when several replicas start at once.
- Marking the web tier unhealthy whenever an optional backend is slow, causing needless cascade failures.
- Depending on `docker compose up` ordering to compensate for an app that cannot reconnect.
- Using `links:` (legacy) to express dependency; service name DNS on the project network already handles discovery ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)).

## 11. Interview Questions

**🎯 Beginner:** _"Your web service lists `depends_on: [db]`, yet it still fails with 'connection refused' at start. Why?"_
**Model answer:** Short-syntax `depends_on` only controls start order: Compose starts the `db` container first, then `web`, without waiting for the database process inside to finish initializing. Postgres, for example, may take several seconds on first boot. The fix is to add a `healthcheck` to `db` (such as `pg_isready`) and change the dependency to `condition: service_healthy`, and also to make the app retry its connection.
_What the interviewer is probing for:_ Knowing started is not ready, and the specific fix.

**🎯 Intermediate:** _"Explain the three `depends_on` conditions and give a use case for each."_
**Model answer:** `service_started` (default) waits for the container to be running, fine for services that tolerate late dependencies or that have no meaningful readiness signal. `service_healthy` waits until the dependency's healthcheck reports healthy, used for databases, brokers and caches. `service_completed_successfully` waits until a one-shot container exits with code 0, used for migrations and seed jobs, and the whole `up` fails if the job exits non-zero. I would add `restart: "no"` on the job and `required: false` for optional dependencies that live in profiles.
_What the interviewer is probing for:_ Precise command of the long syntax and matching it to scenarios.

**🎯 Senior:** _"A health check passes during `up`, but a week later the database restarts and the app stays broken. What is wrong with relying on `depends_on` here, and how do you design for it?"_
**Model answer:** `depends_on` is evaluated when Compose creates or starts containers; it does not supervise the running system, and Docker Engine does not restart a container just because it is unhealthy. So runtime recovery must come from elsewhere: a restart policy for crashes, client-side reconnect with exponential backoff so the app heals when the database returns, and optionally `restart: true` in `depends_on` so a Compose-driven restart of the dependency also restarts the dependent. For unhealthy-but-running cases, add monitoring and an autoheal mechanism or move to an orchestrator. I would verify by killing the database during a test and watching the app recover without human action.
_What the interviewer is probing for:_ Distinguishing start-time ordering from runtime resilience.

**🎯 Architect:** _"Design start-up and upgrade behavior for a Compose stack with a database, a message broker, a migration step, and three replicas of an API, deployed to a single host with minimal downtime."_
**Model answer:** Give `db` and `broker` protocol-aware health checks; a `migrate` job depends on `db` healthy and is idempotent, run once per deploy (`docker compose run --rm migrate` or as a `service_completed_successfully` dependency); the API depends on `migrate` completion and `broker` healthy, and has its own readiness check on a shallow `/healthz`. Replicas are started after the job so only one process migrates. Use expand-and-contract schema changes so old and new API versions work against the same schema during rolling replacement. Deploy with `docker compose up -d --wait --wait-timeout N`, fail the pipeline on timeout, and roll back by redeploying the previous image tag. Clients use retries and backoff because ordering is only a start-time optimization; for true zero-downtime switching, front the API with a reverse proxy and replace replicas gradually ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)), recognizing Compose has no built-in rolling update.
_What the interviewer is probing for:_ Combining ordering, idempotent migrations, readiness, backward-compatible schema changes, and honest limits of Compose.

## 12. Common Misconceptions

- "`depends_on` waits for the service to be ready." Only with `service_healthy` or `service_completed_successfully`, and only if a healthcheck exists.
- "An unhealthy container is restarted automatically." Plain Docker only reports the status.
- "`healthcheck` in the Compose file replaces the Dockerfile `HEALTHCHECK`." It overrides it for that service; `test: ["NONE"]` disables it.
- "`wait-for-it.sh` is required." Modern Compose makes it unnecessary for startup ordering.
- "A health gate protects against later outages." It runs at start time only.
- "`start_period` delays the check." The check still runs; failures in that window simply do not count.

## 13. 🔑 Key Takeaways

- `depends_on` orders start (and reverse-orders shutdown); the default condition does not wait for readiness.
- Use `service_healthy` with a real `healthcheck`, and `service_completed_successfully` for one-shot jobs.
- `docker compose up --wait` blocks until services are running or healthy, and fails on timeout.
- Docker does not heal unhealthy containers; build reconnect logic into clients and monitor health.
- Treat ordering as an optimization, not a correctness guarantee.

## 14. Related Concepts & What's Next

Related: health checks and restart policies ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)), container lifecycle ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), Compose services ([§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), variables ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)), self-healing patterns ([§88](../Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)), integration testing with ephemeral stacks ([§83](../Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)). Next, [§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md) shows how profiles and override files let one project run different sets of services per environment, including optional dependencies.

**Next Section:** [§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md) — `Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md`
