# Section 88 (Part 12): Health Checks and Self-Healing Patterns

## 1. Definition

**Plain language:** A health check is a small command Docker runs inside a container on a timer to ask "are you actually working?" *Self-healing* means the platform reacts to a "no" by itself: restarting the container, replacing it, or taking it out of rotation, without a human.

**Precise definition:** The `HEALTHCHECK` instruction (or `--health-cmd` / Compose `healthcheck:`) registers a probe command stored in the image or container config. The daemon executes it periodically inside the container's namespaces; the exit code sets a state:

- `0` = success (healthy)
- `1` = failure (unhealthy)
- `2` = reserved, do not use

The container's health status moves `starting` → `healthy` or `unhealthy` after `retries` consecutive failures. The key parameters are `interval` (default 30s), `timeout` (30s), `start-period` (0s), `start-interval` (5s, Engine 25+) and `retries` (3). Health is a **status flag and an event**, nothing more: plain Docker Engine does **not** restart a container merely because it is `unhealthy`. Restart *policies* (`on-failure`, `always`, `unless-stopped`) react to the main process **exiting**, and Swarm services additionally replace tasks reported unhealthy ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)). Closing that gap is what "self-healing patterns" are about. The mechanics of the instruction and policies are introduced in [§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md); this section covers design and operations.

> 💡 **Tip:** "Running" means PID 1 exists. "Healthy" means the application answers correctly. A deadlocked server is running and unhealthy.

## 2. Why This Matters

- Processes hang, deadlock, lose their database connection, or exhaust threads without exiting. Restart policies never see these failures.
- Dependency ordering ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)) relies on health to know when a database is ready, not merely started.
- Load balancers, reverse proxies and Swarm use health to decide where to send traffic during deploys ([§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).
- Badly designed checks cause the opposite harm: cascading restarts, flapping, and outages triggered by a slow dependency.
- It is a staple of DCA and SRE interviews because the Docker default (no restart on unhealthy) surprises people.

## 3. Prerequisites and Dependencies

Requires restart policies and the `HEALTHCHECK` syntax ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)), Dockerfile instructions ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md), [§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), container lifecycle and signals ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), and `exec` ([§28](../Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)), since a check *is* an exec. Metrics from [§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md) and logs from [§86](Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md) provide the evidence behind restarts.

## 4. Architecture / Conceptual Diagram

```text
                 HEALTHCHECK (inside container namespaces, via exec)
  dockerd ──every `interval`──► run `test` ──► exit code (or timeout)
     │
     ▼
  ┌──────────┐  first success   ┌──────────┐   `retries` consecutive   ┌───────────┐
  │ starting ├─────────────────►│ healthy  ├──────── failures ────────►│ unhealthy │
  └──────────┘                  └────▲─────┘                           └─────┬─────┘
   (failures during                  │            one success                │
    start-period don't count)        └───────────────────────────────────────┘
                                                    │
                    event: health_status: unhealthy │ (docker events / API)
        ┌───────────────────────────┬──────────────┴────────────┬──────────────────┐
        ▼                           ▼                           ▼                  ▼
  Compose depends_on:         Swarm: replace task      Autoheal sidecar:     Monitoring/alert
  service_healthy gate        and gate rolling update  `docker restart`      (exporter, probe)

  Process EXIT path (separate mechanism):
  main process exits ──► restart policy (no | on-failure[:N] | always | unless-stopped)
                         backoff 100 ms, doubling, capped at 1 min; counter resets after
                         the container runs 10 s
```

- **Two independent loops:** health (is it working?) and restart policy (did it exit?). Plain Docker connects them only if you add something that does.
- **Health is exec-based:** the probe command needs a binary inside the image (`curl`, `wget`, or the app's own subcommand).
- **Each service has one health definition**, so there is no separate liveness/readiness split as in Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 5. Hands-On

### 5.1 Define a Health Check in the Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --start-interval=2s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
CMD ["python", "app.py"]
```

Using the runtime already in the image avoids installing `curl` just for the probe. A non-2xx status makes `urlopen` raise, which also exits non-zero. Probe `127.0.0.1` inside the container, not the published host port.

### 5.2 Watch the State Machine

```bash
docker build -t health-demo .
docker run -d --name hd health-demo
watch -n1 "docker inspect -f '{{.State.Health.Status}} failing={{.State.Health.FailingStreak}}' hd"
docker inspect -f '{{json .State.Health.Log}}' hd | head -c 600
```

```text
starting failing=0
healthy failing=0
```

```text
[{"Start":"2026-10-06T09:00:15Z","End":"2026-10-06T09:00:15Z","ExitCode":0,"Output":""}]
```

`docker inspect` retains only the last five results. `docker ps` shows `(healthy)` or `(health: starting)` in the STATUS column.

### 5.3 Simulate Failure and Observe That Nothing Restarts

```bash
docker exec hd sh -c 'kill -STOP 1'        # freeze the app; process still exists
sleep 60
docker ps --filter name=hd --format '{{.Names}} {{.Status}}'
docker events --since 2m --until 0s --filter container=hd --filter event=health_status
```

```text
hd Up 3 minutes (unhealthy)
2026-10-06T09:02:30 container health_status: unhealthy hd
```

The container stays `Up`. Docker recorded the failure and emitted an event but took no action. That event is the hook for the patterns below.

### 5.4 Restart Policy: Reacts to Exit, Not Health

```bash
docker run -d --name crashy --restart on-failure:3 alpine:3.20 sh -c 'sleep 2; exit 1'
sleep 20
docker inspect -f 'restarts={{.RestartCount}} status={{.State.Status}}' crashy
```

```text
restarts=3 status=exited
```

Use `unless-stopped` for long-running services (survives daemon restarts but respects a manual `docker stop`). Use `on-failure:N` for jobs that must stop retrying eventually. Remember that restarting after an OOM kill ([§31](../Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)) just reproduces the OOM unless the limit or the leak is fixed.

### 5.5 Compose: Health-Gated Startup and Restart

```yaml
services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_pw
    secrets: [db_pw]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d postgres"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 30s
      start_interval: 2s

  api:
    build: .
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
        restart: true          # restart api when db is restarted by a Compose update
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
      interval: 15s
      timeout: 3s
      retries: 3
      start_period: 20s

secrets:
  db_pw:
    file: ./db_pw.txt
```

```bash
docker compose up -d --wait        # blocks until all services are running/healthy, non-zero on failure
```

`--wait` makes health usable in CI scripts. `depends_on` only gates *startup*; it does not stop `api` if `db` later turns unhealthy.

### 5.6 Pattern: Autoheal Sidecar

Plain Docker needs a watcher that turns the `unhealthy` state into `docker restart`. A small community container does exactly this for containers labeled for it:

```yaml
services:
  autoheal:
    image: willfarrell/autoheal:1.2.0
    restart: always
    environment:
      AUTOHEAL_CONTAINER_LABEL: autoheal
      AUTOHEAL_INTERVAL: 10
      AUTOHEAL_START_PERIOD: 60
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
  api:
    image: myorg/api:1.4.2
    labels:
      autoheal: "true"
    healthcheck:
      test: ["CMD", "/app/api", "healthcheck"]
      interval: 15s
      timeout: 3s
      retries: 3
```

Be aware of the trade-off: this requires the Docker socket (see Security Considerations). Swarm replaces unhealthy tasks natively ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)). The equivalent without third-party code is a host `systemd` timer or script that loops on `docker events --filter event=health_status` and runs `docker restart` with rate limiting.

### 5.7 Designing the Endpoint: Shallow vs. Deep

```python
# /healthz  = liveness: process can serve a request (shallow, no dependencies)
# /readyz   = readiness: dependencies reachable (deep, never used for restart decisions)
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/readyz")
def readyz():
    db.execute("SELECT 1")          # raises -> 503
    return {"ready": True}
```

Wire `HEALTHCHECK` to the shallow endpoint when an unhealthy result triggers a restart, and use the deep one for load-balancer or proxy checks (Traefik, HAProxy, Nginx upstream, cloud LB) that only remove the backend from rotation.

## 6. Production Usage Notes

- **Tune timing to the workload:** `start_period` longer than worst-case warm-up (JVM, migrations, cache load); `interval` 10-30 s; `timeout` shorter than `interval`; `retries` 3-5. Failures during `start_period` do not count toward `retries`, but one success ends the period early.
- **Do not make restarts depend on external services.** If the check queries the database and the database blips, every API container turns unhealthy simultaneously and an autoheal tool restarts the whole fleet, turning a blip into an outage.
- **Rate-limit remediation.** Cap restarts (for example three per ten minutes), then stop and page a human. Infinite restart loops hide root causes and mask crash-looping releases ([§93](Section-93-Part12-Troubleshooting-Production-Container-Issues.md)).
- **Exit non-zero on fatal startup errors** (bad config) and let `on-failure:N` limit retries. Do not use `always` for jobs that finish normally.
- **Combine layers:** `restart: unless-stopped` (process died), `HEALTHCHECK` (process wedged), a supervisor or Swarm (replacement), and monitoring alerts on restart counts and unhealthy duration ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)).
- **Make the app crash-only where possible:** on unrecoverable internal state, exit and let the policy restart you. Handle SIGTERM for graceful shutdown ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).
- **Distroless and scratch images** have no shell or `curl` ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)); compile a `healthcheck` subcommand into the application binary, or probe externally.

## 7. Security Considerations

- **Autoheal needs the Docker socket,** which is effectively root on the host ([§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)). A `:ro` mount does not limit API calls. Prefer a host-side script or systemd unit, or front the socket with a filtering proxy (for example `tecnativa/docker-socket-proxy`) that allows only `containers` list and restart.
- **Health output is stored** in `State.Health.Log` and visible to anyone who can `docker inspect`. Never print tokens, connection strings or stack traces with secrets in check output.
- **Do not put credentials on the command line** of the health command (visible in `ps` and inspect). Use files, sockets, or a passwordless local check such as `pg_isready`.
- **Restart loops can hide intrusions or crash exploits** and amplify resource use; alert on restart counts ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Container is `unhealthy` but never restarts | Plain Docker takes no action on health | Add autoheal/host watcher, use Swarm, or exit the process on failure |
| Always `unhealthy`, `Output` says `curl: not found` / `sh: not found` | Probe binary or shell missing (slim, distroless) | Use `CMD` exec form with an existing binary, or build in a healthcheck subcommand |
| Always `unhealthy` right after start | `start_period` too short or probe hits wrong port/host | Increase `start_period`; probe `127.0.0.1` and the container's listening port |
| Probe passes locally, fails in container | App binds to `127.0.0.1` vs `0.0.0.0`, or IPv6 `localhost` resolves to `::1` | Use `127.0.0.1` in the probe; bind the app correctly |
| `CMD-SHELL` check silently passes | Shell pipeline hides the exit code (`curl ... | grep`) | Use `set -o pipefail` or `curl -fsS` and `|| exit 1` |
| `depends_on: service_healthy` hangs, `dependency failed to start` | Dependency never became healthy | `docker inspect` its Health log; fix probe or increase retries |
| Flapping healthy/unhealthy | Timeout shorter than p99 latency, or CPU throttled ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)) | Raise timeout and retries; check throttling and limits |
| Restart count climbing, exit 137 | OOM kill or `docker stop` timeout kill | Check `State.OOMKilled`, memory limit, `STOPSIGNAL` |

## 9. Best Practices

- Define a `HEALTHCHECK` for every long-running service, in the Dockerfile so it travels with the image, and override in Compose only when environment-specific.
- Use exec form probes with binaries already present; keep them fast, read-only and idempotent.
- Separate shallow liveness (restart decisions) from deep readiness (routing decisions).
- Set `start_period` generously, `timeout` below `interval`, and `retries` of at least 3.
- Pair `restart: unless-stopped` with health-gated `depends_on` and `docker compose up --wait`.
- Rate-limit automated remediation and alert when it triggers.
- Test failure paths: freeze, kill and OOM a staging container and confirm the system recovers and alerts.
- Make services tolerate dependency outages with retries, backoff and timeouts, so recovery does not rely on restarts.

## 10. Common Anti-Patterns / Mistakes

- Assuming `unhealthy` triggers a restart in plain Docker.
- A deep health check (database, third-party API) that triggers fleet-wide restarts during a dependency outage.
- `HEALTHCHECK CMD curl localhost` in an image without `curl`, so it is permanently unhealthy.
- `restart: always` on everything, including one-shot jobs and crash-looping misconfigurations.
- Mounting the Docker socket read-write into a general-purpose container for remediation.
- No `start_period`, so slow applications are marked unhealthy during normal boot.

## 11. Interview Questions

**🎯 Beginner:** _"What does a Docker `HEALTHCHECK` do, and what happens to a container that becomes `unhealthy`?"_
**Model answer:** It runs a command inside the container on an interval; exit 0 means healthy, 1 unhealthy. After the configured number of consecutive failures (default 3) the status becomes `unhealthy`, visible in `docker ps` and `docker inspect`, and a `health_status` event is emitted. With plain Docker nothing else happens: the container keeps running and is not restarted. Swarm will replace the task, Compose can gate dependents with `service_healthy`, and you can add a watcher to restart it.
_What the interviewer is probing for:_ Knowing health is a status signal and that Docker alone does not self-heal on it.

**🎯 Intermediate:** _"An app container sometimes deadlocks. `restart: always` is set, yet it stays down for hours. Why, and what do you change?"_
**Model answer:** A deadlocked process has not exited, so the restart policy never fires. I add a liveness-style `HEALTHCHECK` against a shallow endpoint to surface the state, then make something act on it: Swarm service, an autoheal watcher built on `docker events`, or a supervisor. Better still, add an internal watchdog so the app exits when its worker loop stalls, which restores the policy-based path. I would also alert on unhealthy duration and capture a thread dump before restart for the postmortem.
_What the interviewer is probing for:_ Distinguishing exit-driven restarts from health-driven remediation, and building both.

**🎯 Senior:** _"After a database outage, your whole API fleet restarted repeatedly and prolonged recovery. What went wrong and how would you redesign health and restart behavior?"_
**Model answer:** The health check probably queried the database, so every instance became unhealthy at once and the autoheal tool restarted them all, dropping connections, emptying caches and causing a thundering herd on the recovering database. I separate liveness from readiness: the container check tests only that the process responds; dependency state feeds readiness, which removes instances from the load balancer without restarting them. I add connection retries with exponential backoff and jitter, a restart rate limit and cool-down in the remediation tool, `start_period` for warm-up, and alerts on correlated restarts. Then I rehearse the dependency failure in staging to prove the system degrades rather than collapses.
_What the interviewer is probing for:_ Failure-mode thinking, avoiding cascading failure, and the liveness/readiness distinction.

**🎯 Architect:** _"Define the self-healing strategy for 200 services across Docker hosts today and an expected Kubernetes migration."_
**Model answer:** Define a platform contract: every service ships a `HEALTHCHECK` plus `/healthz` (liveness) and `/readyz` (readiness) endpoints, handles SIGTERM, has resource limits and is safe to restart (idempotent startup, no local state). On Docker hosts, enforce it with templates (Compose or Swarm) that set restart policy, health timings, stop grace, and an orchestrated remediation layer with bounded retries, plus fleet metrics and alerts on restart rate and time-unhealthy. Because the contract maps one-to-one onto Kubernetes liveness, readiness and startup probes, `terminationGracePeriodSeconds`, and requests/limits, the migration changes manifests, not applications. Governance: CI lints that reject images without a health definition, game-day failure injection, and an SLO-based escalation path when automatic remediation exceeds its budget.
_What the interviewer is probing for:_ Platform thinking, standardized contracts, bounded automation, and migration-ready design ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 12. Common Misconceptions

- "`restart: always` fixes unhealthy containers." It only reacts to process exit.
- "A healthy container means a healthy application." It means the probe passed; the probe may be shallow or wrong.
- "`depends_on` keeps dependents running only while the dependency is healthy." It gates startup (and optionally restarts on Compose updates), not ongoing health.
- "Docker has liveness and readiness probes." It has one health check; the split is a design convention (or Kubernetes).

## 13. 🔑 Key Takeaways

- Health = status plus event; restart policy = reaction to process exit; the two are separate and plain Docker does not link them.
- Self-healing in Docker needs Swarm, a bounded watcher, or an app that exits when broken.
- Keep restart-triggering checks shallow; put dependency checks in readiness for routing.
- Set `start_period`, sensible `timeout` and `retries`; probe `127.0.0.1` with binaries present in the image.
- Rate-limit and alert on automated restarts; never mount the socket carelessly.
- Use `depends_on: condition: service_healthy` and `docker compose up --wait` for ordered, verifiable startup.

## 14. Related Concepts & What's Next

Related: restart policies and `HEALTHCHECK` basics ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)), Compose dependency ordering ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), monitoring ([§87](Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)), Swarm ([§90](Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)), zero-downtime deploys ([§91](Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)). Next, [§89](Section-89-Part12-Resource-Management-at-Scale.md) covers how limits, quotas and capacity planning keep many containers from starving each other.

**Next Section:** [§89](Section-89-Part12-Resource-Management-at-Scale.md) — `Section-89-Part12-Resource-Management-at-Scale.md`
