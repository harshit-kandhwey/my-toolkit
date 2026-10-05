# Section 40 (Part 5): Compose CLI Deep Dive: up, down, logs, exec

## 1. Definition

**Plain language:** The Compose CLI is the set of `docker compose ...` subcommands you use to create, inspect, change and destroy the whole application described by your Compose file: `up` builds and starts it, `ps` and `logs` show it, `exec` and `run` get you inside it, `down` removes it.

**Precise definition:** Compose v2 is a Go plugin of the Docker CLI (`docker compose`, no hyphen; the Python `docker-compose` v1 binary reached end of life in 2023). It reads the merged Compose model ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), then reconciles the Docker Engine to match it through the Engine API. Every container, network and volume it creates carries `com.docker.compose.project`, `com.docker.compose.service` and related labels. Those labels, not a local state file, are how later commands find "the project". The project name comes from, in priority order: `-p/--project-name`, `COMPOSE_PROJECT_NAME`, the top-level `name:` key, then the project directory basename.

> 💡 **Tip:** `docker compose up` is declarative and idempotent: it diffs the desired state against running containers and only recreates services whose configuration hash changed.

## 2. Why This Matters

- Most day-to-day Docker work on a developer machine, and a lot of single-host deployments, goes through these dozen commands.
- Knowing the difference between `stop`, `down`, `down -v` and `rm` is the difference between a restart and silently destroying a database volume.
- `up` has flags (`--build`, `--force-recreate`, `--no-deps`, `--wait`, `--abort-on-container-exit`) that change behavior in CI versus local work.
- `run` versus `exec` versus `up` is a frequent source of confusion: one creates a new container, one enters an existing one.
- Reading logs and events efficiently shortens debugging loops considerably.

## 3. Prerequisites and Dependencies

You need a Compose file ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), [§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), a working Engine ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)) and the plain Docker commands that Compose wraps: `docker run` ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), lifecycle ([§27](../Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)), `exec` ([§28](../Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)), logs ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)) and cleanup ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)). Variable interpolation ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)), `depends_on` ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), profiles and overrides ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)) and `--scale` ([§39](Section-39-Part5-Scaling-Services-with-Compose.md)) all change what these commands act on.

## 4. Architecture / Conceptual Diagram

```text
  docker compose [GLOBAL FLAGS] <command> [FLAGS] [SERVICE...]
  Global: -f file (repeatable)  --profile P  -p name  --env-file F  --project-directory D

   compose files + .env + profiles
              │  load, interpolate, merge, validate  (docker compose config shows this)
              ▼
        ┌────────────────┐   diff vs. labelled containers   ┌────────────────────┐
        │ Desired model  │ ───────────────────────────────► │ Engine API (dockerd)│
        └────────────────┘   create / start / recreate      └─────────┬──────────┘
                                                                      ▼
                                          project "shop"  (label com.docker.compose.project=shop)
                                          ├─ shop-web-1   shop-web-2   (service web, replicas)
                                          ├─ shop-db-1
                                          ├─ network shop_default
                                          └─ volume  shop_pgdata

  Lifecycle commands and what they touch
  ┌───────────┬────────────┬──────────┬───────────┬─────────────────────────────┐
  │ command   │ containers │ networks │ volumes   │ images                      │
  ├───────────┼────────────┼──────────┼───────────┼─────────────────────────────┤
  │ stop      │ stopped    │ kept     │ kept      │ kept                        │
  │ down      │ removed    │ removed  │ kept      │ kept                        │
  │ down -v   │ removed    │ removed  │ REMOVED*  │ kept                        │
  │ down --rmi│ removed    │ removed  │ kept      │ removed (all / local)       │
  │ rm        │ removed (stopped only)   │ kept     │ kept                      │
  └───────────┴────────────┴──────────┴───────────┴─────────────────────────────┘
  * named volumes declared in the file and anonymous volumes; external: true volumes are never removed
```

- **Selectors:** most commands accept service names; with none, they act on every enabled service in the active profiles.
- **Exit codes:** `up --abort-on-container-exit --exit-code-from SVC` makes the CLI return that service's exit code, which is how CI uses Compose as a test runner.
- **No daemon of its own:** Compose holds no state beyond Engine labels and its short-lived process, so you can run it from any machine that can reach the Engine (`DOCKER_HOST`, contexts).

## 5. Hands-On

The examples use this small project, saved as `compose.yaml` (the preferred file name, with `docker-compose.yml` still accepted):

```yaml
name: shop
services:
  web:
    build: ./web
    ports: ["8080:80"]
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: example
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 10
volumes:
  pgdata:
```

### 5.1 up: Create and Start

```bash
docker compose up -d                  # detached
docker compose up -d --build          # rebuild images first
docker compose up -d --wait           # return only when services are running/healthy
docker compose up --force-recreate    # recreate containers even if config unchanged
docker compose up -d --no-deps web    # only web, do not start or recreate db
docker compose up -d --remove-orphans # remove containers for services deleted from the file
docker compose up -d --pull always    # pull newer images first (missing | always | never)
```

```text
[+] Running 4/4
 ✔ Network shop_default   Created
 ✔ Volume "shop_pgdata"   Created
 ✔ Container shop-db-1    Healthy
 ✔ Container shop-web-1   Started
```

Without `-d`, `up` runs attached: it multiplexes all logs with coloured service prefixes, and Ctrl+C stops the containers. `--abort-on-container-exit` and `--exit-code-from` give the CI behavior described above.

### 5.2 ps, top, images, ls: Status

```bash
docker compose ps
docker compose ps -a --format json
docker compose ps --status running --services
docker compose top
docker compose images
docker compose ls -a            # every Compose project on this Engine
```

```text
NAME         IMAGE        COMMAND                  SERVICE   STATUS                  PORTS
shop-db-1    postgres:16  "docker-entrypoint.s…"   db        Up 2 minutes (healthy)  5432/tcp
shop-web-1   shop-web     "nginx -g 'daemon of…"   web       Up 2 minutes            0.0.0.0:8080->80/tcp
```

### 5.3 logs: Reading Output

```bash
docker compose logs                      # everything, all services
docker compose logs -f --tail=50 web     # follow, last 50 lines
docker compose logs -t --since 10m db    # timestamps, last ten minutes
docker compose logs --no-log-prefix web  # raw lines, handy for piping
```

`logs` reads through the Engine's logging driver ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)); with a driver that has no local read support, such as `syslog` or `fluentd`, nothing can be shown.

### 5.4 exec versus run

```bash
docker compose exec db psql -U postgres          # enter the RUNNING db container (TTY by default)
docker compose exec -T web cat /etc/hostname     # -T disables the TTY; required in cron and CI pipes
docker compose exec --index 2 web sh             # second replica of a scaled service
docker compose exec -u root -e DEBUG=1 web sh

docker compose run --rm web python manage.py migrate   # NEW one-off container
docker compose run --rm --no-deps -e FOO=bar web sh    # do not start linked services
docker compose run --rm --service-ports web            # publish the service's ports (off by default)
docker compose run --rm --entrypoint sh web
```

`exec` needs a running container; `run` creates a fresh container from the service definition (same image, env, volumes and networks), starts dependencies unless `--no-deps`, and by default does **not** publish the service's `ports:` to avoid host-port clashes.

### 5.5 Stopping, Restarting and Removing

```bash
docker compose stop            # SIGTERM, then SIGKILL after stop_grace_period (default 10s)
docker compose start           # start existing stopped containers
docker compose restart web     # restart without re-reading the Compose file changes
docker compose pause web && docker compose unpause web
docker compose kill -s SIGHUP web
docker compose rm -f -s        # stop (-s) and remove containers
docker compose down            # remove containers and networks
docker compose down -v         # ALSO remove volumes; deletes data
docker compose down --rmi local --remove-orphans
```

`restart` does not apply edits to the Compose file; `up -d` does, because it recreates the changed service. Use `up -d` after changing image, env or ports.

### 5.6 config, build, pull, push, cp, events, wait, watch

```bash
docker compose config                 # fully merged, interpolated model (first debugging step)
docker compose config --quiet         # validate only; non-zero exit on error
docker compose config --services
docker compose config --images
docker compose build --no-cache web
docker compose build --build-arg VERSION=1.2 web
docker compose pull --quiet
docker compose push
docker compose cp web:/app/log.txt ./log.txt
docker compose events --json
docker compose port web 80
docker compose wait db                # block until the container stops, print exit code
docker compose watch                  # file-sync or rebuild on change, see Section 41
```

### 5.7 Targeting Files, Profiles and Projects

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
docker compose --profile debug up -d
docker compose -p shop-staging --env-file .env.staging up -d
COMPOSE_FILE=compose.yaml:compose.dev.yaml docker compose ps
docker compose --dry-run up -d        # print the planned operations without applying
```

`--dry-run` is a global flag in Compose v2. It is a good first run for any unfamiliar destructive command.

### 5.8 Shell Completion and Environment Variables

```bash
docker compose completion bash > /etc/bash_completion.d/docker-compose
export COMPOSE_BAKE=true      # build via buildx bake (default behavior in recent releases)
export COMPOSE_PROGRESS=plain # CI-friendly progress output (auto | tty | plain | json | quiet)
export COMPOSE_PARALLEL_LIMIT=2
```

## 6. Production Usage Notes

- **Compose on a single host** is common for small production workloads, internal tools and CI. Pin images by tag or digest, set `restart: unless-stopped`, define healthchecks ([§32](../Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md)) and use `up -d --wait` in deploy scripts so a failed rollout returns non-zero.
- **Deploy script shape:** `docker compose pull && docker compose up -d --remove-orphans --wait`. Only services with new images get recreated.
- **CI test runs:** `docker compose up --build --abort-on-container-exit --exit-code-from tests`, then `docker compose down -v` in an `always` step so volumes do not leak between jobs.
- **Always pass the same `-f`/`-p`/`--env-file` set** to every command in a session; otherwise `down` may target a different project than `up` created. Put them in `COMPOSE_FILE` and `COMPOSE_PROJECT_NAME` (or a `.env`) to make that automatic.
- **Remote Engines:** `docker --context prod compose up -d` or `DOCKER_HOST=ssh://user@host` runs the plan against a remote host without copying the project there; bind-mounted paths then resolve on the remote host, not your laptop.
- **Graceful shutdown:** raise `stop_grace_period` for databases and queue workers so `stop` and `down` do not SIGKILL mid-write.
- **Parallelism:** Compose starts independent services concurrently; `depends_on` ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)) is the only ordering guarantee.

## 7. Security Considerations

- **`config` prints resolved secrets.** Interpolated environment values appear in clear text; do not paste its output into tickets or CI logs. Use `--no-interpolate` or `--no-env-resolution` when sharing structure only.
- **Access to the Docker socket is root-equivalent**, and Compose uses it. Restrict who can run `docker compose` on shared hosts, and prefer remote contexts over SSH with limited accounts.
- **`exec -u root` and `run --entrypoint`** bypass the intended user and entrypoint. Audit-sensitive environments should record Engine events rather than trust the CLI.
- **`run` inherits service environment**, including credentials; one-off containers also inherit mounts, so a bad command can write to production volumes.
- **`down -v` and `--rmi all`** are destructive; guard them in scripts, and never point them at a project name you derived from user input.
- **`logs` may contain secrets** that applications print; apply log-driver retention limits ([§29](../Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)).
- **Untrusted Compose files** can mount `/`, add `privileged: true` or publish the Docker socket; read a file (`docker compose config`) before running one from a third party.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `no configuration file provided: not found` | Wrong directory or file name | `cd` to the project, or pass `-f` / `--project-directory` |
| `docker: 'compose' is not a docker command` | Compose plugin not installed | Install `docker-compose-plugin` (Linux) or update Docker Desktop |
| `down` leaves the old stack running | Different project name or file set than `up` | Match `-p`/`-f`, or list with `docker compose ls` |
| Edits to `compose.yaml` ignored | Used `restart` instead of `up -d` | Run `docker compose up -d` |
| Code change not in the container | Image not rebuilt | `docker compose up -d --build` |
| `Bind for 0.0.0.0:8080 failed: port is already allocated` | Another container or process holds the port | `docker compose ps`, `ss -ltnp`, change the host port |
| `the input device is not a TTY` in CI | `exec` allocates a TTY by default | Add `-T` |
| Orphan warning on `up` | Service removed from the file, container remains | `--remove-orphans` |
| Data gone after `down` | `-v` used, or volume was anonymous | Use named volumes; never `-v` casually |
| `variable is not set. Defaulting to a blank string` | Missing env value | Provide `.env`, `${VAR:?error}` syntax or `--env-file` |
| `logs` shows nothing | Non-local logging driver | Check `docker inspect` log driver; read from the backend |
| `run` works but `up` fails | Different dependencies and ports behavior | Compare with `docker compose config` and logs of the dependency |

## 9. Best Practices

- Run `docker compose config --quiet` in CI as a lint step.
- Use `up -d --wait` in scripts and `--wait-timeout` to bound it.
- Prefer `run --rm` for migrations and admin tasks so one-off containers disappear.
- Use `exec -T` anywhere there is no terminal.
- Keep `COMPOSE_PROJECT_NAME` (or `name:`) stable and explicit, especially in CI where checkout directories vary.
- Use `down --remove-orphans` as the normal teardown, and `-v` only where throwaway data is intended.
- Use `--dry-run` before unfamiliar bulk operations.
- Tail logs with `-f --tail` rather than unbounded `logs`, and use `--since` to narrow incidents.
- Use `docker compose events` or `ps --format json` for automation instead of scraping table output.

## 10. Common Anti-Patterns / Mistakes

- Using the removed `docker-compose` v1 command and v1-only features (`version:` keys are now ignored and obsolete).
- Running `docker compose down -v` as a "reset" on a stack that holds a real database.
- Using `restart` to deploy a changed file.
- Running `exec` into a container, editing files by hand and treating the change as persistent.
- Using `run` for a long-lived service instead of `up`.
- Calling `docker rm` or `docker stop` directly on Compose containers, which leaves Compose's expectations out of sync with reality (it will simply recreate them next `up`).
- Using `up` attached in production over SSH and losing the stack when the session drops.
- Relying on container name patterns (`shop_web_1`, with underscores) from v1; v2 uses hyphens, and scripts should use `docker compose ps -q web` instead.
- Passing different `-f` sets between `up` and `down`.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `docker compose stop`, `down` and `down -v`?"_
**Model answer:** `stop` stops the containers but leaves them, their networks and volumes in place, so `start` brings the same containers back. `down` stops and removes containers and the project's networks, but keeps named volumes and images, so data survives and the next `up` recreates containers. `down -v` additionally removes volumes declared in the Compose file and anonymous volumes, which deletes persisted data such as database files. Volumes marked `external: true` are never removed. In practice, `down` is the normal teardown and `-v` is a deliberate reset.
_What the interviewer is probing for:_ Awareness of what is destroyed at each level, and respect for volumes.

**🎯 Intermediate:** _"When do you use `docker compose exec`, and when `docker compose run`? What surprises people about `run`?"_
**Model answer:** `exec` runs an extra process inside an already running container of a service, so it shares the same filesystem state and processes; use it for shells, `psql`, inspecting a live app. `run` creates a new container from the service definition, optionally overriding the command, and is right for one-off tasks such as migrations, test runs or seeding. Surprises: `run` starts linked dependencies unless `--no-deps`, does not publish the service's ports unless `--service-ports`, leaves the container behind unless `--rm`, and uses the image, not changed files inside the live container. For automation, `exec -T` avoids TTY errors.
_What the interviewer is probing for:_ A clear mental model of existing versus new containers and the practical flags.

**🎯 Senior:** _"A deploy script runs `docker compose pull && docker compose up -d`. A bad image reaches production and the script still exits 0. How do you make this safer?"_
**Model answer:** `up -d` returns once containers are started, not once they are healthy. Add healthchecks to services and use `up -d --wait --wait-timeout N`, which returns non-zero if any service fails to become running or healthy, so the pipeline can trigger rollback. Pin the image by digest or immutable tag, and keep the previous tag recorded so rollback is `IMAGE_TAG=<old> docker compose up -d`. Use `--remove-orphans`, run `config --quiet` first, and use `--dry-run` for review. Note this is not zero-downtime; for that, put a proxy in front and roll replicas, or use an orchestrator ([§91](../Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)).
_What the interviewer is probing for:_ Understanding of `--wait`, healthchecks and rollback in a Compose-based deployment.

**🎯 Architect:** _"A team uses Compose for local development, CI integration tests and a single-host production deployment. How do you structure the CLI usage and files so the three do not diverge dangerously?"_
**Model answer:** Keep one base `compose.yaml` with service definitions that are true everywhere, and layer environment-specific files (`compose.override.yaml` for dev bind mounts and debug ports, `compose.ci.yaml`, `compose.prod.yaml`) selected explicitly with `-f` or `COMPOSE_FILE`, plus profiles for optional tools ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)). Parameterize with `.env` files per environment ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)) and use `${VAR:?}` for required values. CI uses `up --abort-on-container-exit --exit-code-from` and `down -v`; production uses digest-pinned images, `up -d --wait`, restart policies and external volumes so `down` cannot erase data. Lint with `config --quiet` for every environment, and document the point where a single host stops being enough, which leads to Swarm or Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).
_What the interviewer is probing for:_ Layered configuration design, safe defaults per environment, and knowing the limits of Compose.

## 12. Common Misconceptions

- "`docker-compose` and `docker compose` are the same." The first is the retired Python v1 tool; the second is the supported Go plugin with different naming and behavior.
- "`restart` picks up my YAML changes." It only restarts the existing containers.
- "`down` deletes my data." Not without `-v`.
- "`exec` and `run` are interchangeable." One enters a running container; the other creates a new one.
- "`up -d` means the app is ready." It means the containers started; readiness needs `--wait` and healthchecks.
- "Compose remembers the project in a state file." It discovers it from Engine labels.

## 13. 🔑 Key Takeaways

- `up -d` is idempotent and recreates only changed services; `--wait` makes it a readiness gate.
- `stop` keeps everything, `down` removes containers and networks, `down -v` also removes volumes.
- `exec` enters an existing container; `run --rm` makes a throwaway one.
- Use `-T` with `exec` in non-interactive contexts.
- `docker compose config` shows the real merged, interpolated model, and may print secrets.
- Keep project name, file set and env file identical across commands.
- `--dry-run`, `ps --format json`, and `events` support safe, scriptable operation.

## 14. Related Concepts & What's Next

Related: file format ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), services/networks/volumes ([§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), variables ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)), ordering ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), profiles ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)), scaling ([§39](Section-39-Part5-Scaling-Services-with-Compose.md)), and the underlying Docker commands in Part 4. Next, [§41](Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md) applies these commands to the inner development loop: bind mounts, hot reload and `compose watch`.

**Next Section:** [§41](Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md) — `Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md`
