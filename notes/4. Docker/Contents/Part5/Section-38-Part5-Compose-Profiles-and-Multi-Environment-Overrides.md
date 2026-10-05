# Section 38 (Part 5): Compose Profiles and Multi-Environment Overrides

## 1. Definition

**Plain language:** One Compose project usually has to behave differently on a laptop, in CI and in production. Compose gives you two tools for that. **Profiles** decide *which services* run (a debug UI, a seed job, a test runner). **Multiple files and overrides** decide *how the services that run are configured* (bind mounts in dev, resource limits in prod).

**Precise definition:**

- A **profile** is a label attached to a service through the `profiles:` attribute. A service with no `profiles:` is always part of the project. A service with one or more profiles is started only when at least one of its profiles is active, or when you name that service explicitly on the command line. Profiles are activated with `--profile <name>` (repeatable) or the `COMPOSE_PROFILES` environment variable (comma-separated).
- **Multiple Compose files** are merged in order. `docker compose` reads `compose.yaml` (or `docker-compose.yml`) plus the optional `compose.override.yaml` (or `docker-compose.override.yml`) automatically. With `-f a.yaml -f b.yaml` (or `COMPOSE_FILE`) you take control of the exact list, and later files override earlier ones according to Compose Specification merge rules. The top-level `include:` element and the service-level `extends:` attribute offer composition instead of override.

> 💡 **Tip:** Run `docker compose config` after every change to a file list or profile set. It prints the fully merged and interpolated model, which is the only reliable answer to "what will actually run?".

## 2. Why This Matters

- Without profiles, teams keep one-off services (`adminer`, `mailhog`, migrations, load generators) in separate files or comment them out, and the project drifts.
- Without a clean override strategy, dev-only settings (`ports`, bind mounts, `DEBUG=1`) leak into production, or production files get copied and edited per environment.
- Misunderstanding merge rules is the most common cause of "my override did nothing" and "my port is published twice".
- It is the Compose-level analogue of Kustomize overlays or Helm values, and an interview favorite for "how do you manage environments with Compose?".

## 3. Prerequisites and Dependencies

Requires the file format and merge model from [§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), the service, network and volume vocabulary from [§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md), and variable interpolation and `.env` handling from [§36](Section-36-Part5-Environment-Variables-and-env-Files.md), because per-environment settings often come from env files. Dependency ordering ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)) interacts with profiles: a service cannot depend on a service that is not enabled. The CLI behaviors used here (`up`, `run`, `config`) are explored in [§40](Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md), and the dev workflow that relies on override files is in [§41](Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md).

## 4. Architecture / Conceptual Diagram

```text
  PROFILES: which services exist in this run?

   compose.yaml
   ┌───────────────────────────────────────────────────────────┐
   │ web        (no profiles)     ──────────────► always runs  │
   │ db         (no profiles)     ──────────────► always runs  │
   │ adminer    profiles: [debug] ──┐                          │
   │ migrate    profiles: [tools] ──┼─► run only if profile on │
   │ k6         profiles: [perf]  ──┘   or named explicitly    │
   └───────────────────────────────────────────────────────────┘
        docker compose up                          ► web, db
        docker compose --profile debug up          ► web, db, adminer
        COMPOSE_PROFILES=debug,perf docker compose up ► web, db, adminer, k6
        docker compose run migrate                 ► migrate (auto-enabled)

  OVERRIDES: how is each service configured?

   compose.yaml  (base, valid on its own)
        │  merged with ◄─ later file wins
        ▼
   compose.override.yaml     ◄── picked up automatically (dev)
        or
   -f compose.yaml -f compose.prod.yaml   ◄── explicit (prod)
        │
        ▼
   merged model  ──► docker compose config  ──► docker compose up

  Merge rules (per attribute type):
  ┌──────────────────────┬─────────────────────────────────────────┐
  │ scalar (image, ...)  │ later value REPLACES earlier            │
  │ mapping (environment,│ merged key by key, later key wins       │
  │   labels, build args)│                                         │
  │ sequence (ports,     │ APPENDED (ports/volumes de-duplicated   │
  │   expose, dns, ...)  │ by target); command/entrypoint REPLACED │
  │ !reset / !override   │ explicit tags to clear or replace       │
  └──────────────────────┴─────────────────────────────────────────┘
```

- **Profiles filter services; overrides edit services.** They compose: a prod override file can also add or remove profiles.
- **The base file should be valid alone.** Overrides then only add environment-specific deltas.
- **Relative paths** in every file are resolved against the directory of the **first** `-f` file (the project directory), not the override's own location, unless you set `--project-directory`.

## 5. Hands-On

### 5.1 A Project With Profiles

```yaml
# compose.yaml
name: shop
services:
  web:
    build: .
    ports: ["8080:8000"]
    environment:
      DATABASE_URL: postgres://app:app@db:5432/app
    depends_on:
      db: { condition: service_healthy }

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
      POSTGRES_DB: app
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes: [pgdata:/var/lib/postgresql/data]

  adminer:                      # debug UI
    image: adminer:4
    profiles: ["debug"]
    ports: ["127.0.0.1:8081:8080"]

  migrate:                      # one-shot job
    build: .
    command: ["python", "manage.py", "migrate"]
    profiles: ["tools"]
    depends_on:
      db: { condition: service_healthy }

volumes:
  pgdata:
```

### 5.2 Activating Profiles

```bash
docker compose up -d                          # web, db only
docker compose --profile debug up -d          # + adminer
COMPOSE_PROFILES=debug,tools docker compose up -d
docker compose --profile "*" up -d            # every profile
docker compose config --profiles              # list known profile names
docker compose config --services              # services in the active set
```

```text
debug
tools
```

### 5.3 Targeting a Profiled Service Explicitly

```bash
docker compose run --rm migrate
```

Naming a service on the command line (`run`, `up migrate`) activates that service's profiles automatically. You do not need `--profile tools` for a one-off job. This is why profiles suit migrations, seeders and backup jobs.

### 5.4 The Dependency Trap

```yaml
services:
  web:
    image: myapp
    depends_on: [cache]          # cache has a profile, web does not
  cache:
    image: redis:7-alpine
    profiles: ["cache"]
```

```bash
docker compose up
```

```text
service "web" depends on undefined service "cache": invalid compose project
```

A non-profiled service must not require a profiled one unless that profile is active. Either remove the profile from `cache`, give `web` the same profile, or make the dependency itself part of a profiled service. Profiled services may depend on other services in the same profile, or on always-on services.

### 5.5 Automatic Override File (Development)

```yaml
# compose.override.yaml  (read automatically next to compose.yaml)
services:
  web:
    build:
      target: dev
    command: ["python", "manage.py", "runserver", "0.0.0.0:8000"]
    environment:
      DEBUG: "1"
    volumes:
      - ./src:/app/src
```

```bash
docker compose up -d        # base + override, no flags needed
docker compose config web   # prove the merge
```

### 5.6 Explicit Files (Production)

```yaml
# compose.prod.yaml
services:
  web:
    image: registry.example.com/shop/web:${TAG:?TAG is required}
    build: !reset null            # do not build in prod; pull the image
    restart: unless-stopped
    ports: !override
      - "127.0.0.1:8000:8000"    # replace, do not append
    environment:
      DEBUG: "0"
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 512M }
  db:
    restart: unless-stopped
```

```bash
TAG=1.4.2 docker compose -f compose.yaml -f compose.prod.yaml config
TAG=1.4.2 docker compose -f compose.yaml -f compose.prod.yaml up -d
```

With explicit `-f`, `compose.override.yaml` is **not** read. That is the point: production never inherits dev bind mounts by accident.

### 5.7 Merge Rules in Practice

```yaml
# base
services:
  web:
    ports: ["8080:8000"]
    environment: { A: "1", B: "1" }
    command: ["gunicorn", "app:app"]
# override
services:
  web:
    ports: ["9090:8000"]
    environment: { B: "2", C: "3" }
    command: ["python", "-m", "debugpy"]
```

```text
ports:       8080:8000 AND 9090:8000      (sequences append)
environment: A=1, B=2, C=3                (mapping merged, later wins)
command:     ["python","-m","debugpy"]    (command is replaced, not appended)
```

Use `!override` to replace a sequence wholesale and `!reset` to clear an attribute or remove an inherited item. Both tags need a reasonably recent Compose v2 plugin (introduced in the 2.2x series); check with `docker compose version`.

### 5.8 Composition Alternatives: `include` and `extends`

```yaml
# compose.yaml
include:
  - path: ./observability/compose.yaml     # separate model, own project dir
  - path:
      - ./shared/compose.yaml
      - ./shared/compose.dev.yaml          # list = merged first
    env_file: ./shared/.env

services:
  api:
    extends:
      file: ./shared/service-base.yaml
      service: python-base
    environment:
      LOG_LEVEL: info
```

- `include` pulls in a complete sub-model, with its own relative paths, and **conflicting resource names are an error** rather than a silent merge. It suits ownership boundaries (platform team ships a monitoring stack).
- `extends` reuses one service definition. It does not copy `depends_on`, `links` or `volumes_from` relationships to other services.

## 6. Production Usage Notes

- **Keep the base file environment-neutral** (images, healthchecks, networks, internal ports). Put replicas, restart policies, limits, host ports and log options in `compose.prod.yaml`.
- **Commit** `compose.yaml`, `compose.override.yaml` (dev defaults) and `compose.prod.yaml`; **do not commit** `.env` files holding secrets.
- **Gate CI** on `docker compose -f ... config -q` for each file combination so syntax and merge errors fail the build, not the deploy.
- **Pin the file list in the deploy command or script**, not in a developer-editable `.env`.
- **Use profiles for operational jobs** (`migrate`, `backup`, `seed`) and run them with `docker compose run --rm`.
- **Use `docker compose config --no-interpolate`** to review a template, and the interpolated form (default) to see what the daemon receives.
- Compose is single-host. For multi-host production use Swarm ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)) or Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)); `docker compose` in prod is reasonable for small, single-node deployments.

## 7. Security Considerations

- **Dev conveniences are attack surface.** Published debug UIs (`adminer`, `pgadmin`), `DEBUG=1`, host bind mounts and mounted Docker sockets must live only in dev overrides or behind an opt-in profile. Bind such UIs to `127.0.0.1`.
- **A profile is not an access control.** Anyone who can run `docker compose` can enable any profile. Treat profiled admin tools as exposed if the host is shared.
- **Never put secrets in committed override files.** Use env files outside version control, `secrets:` entries ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), or injected CI variables. Use `${VAR:?message}` so a missing secret fails loudly.
- **Merge surprises can widen exposure.** Because `ports` appends, a dev override can silently add a published port to a production stack if `compose.override.yaml` is loaded. Use explicit `-f` lists in production.
- **Review the rendered model** (`docker compose config`) in code review for privileged flags, `network_mode: host`, extra capabilities and mounts.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Profiled service never starts with `up` | No profile active | `--profile name`, `COMPOSE_PROFILES`, or name the service |
| `depends on undefined service` | Non-profiled service depends on profiled one | Align profiles or drop the dependency |
| Override ignored | File not loaded (explicit `-f` skips the override file) or wrong filename | `docker compose config`; add `-f` explicitly |
| Port published twice / bind error | `ports` sequences appended | Use `!override`, or keep ports out of the base |
| Prod container has dev bind mounts | `compose.override.yaml` auto-loaded | Use explicit `-f compose.yaml -f compose.prod.yaml` |
| Relative path points to wrong dir | Paths resolve from first file's directory | Use `--project-directory` or `include` with `project_directory` |
| `!reset`/`!override` parse error | Older Compose plugin | Upgrade Compose v2; check `docker compose version` |
| `command` seems doubled | Expected append | `command` and `entrypoint` replace, they do not append |
| Variables empty in override | Interpolation uses project `.env`, not the override's folder | Pass `--env-file` explicitly |
| Two stacks clobber each other | Same project name | `-p` / `name:` / `COMPOSE_PROJECT_NAME` |

## 9. Best Practices

- Make the base file runnable on its own, then layer environment files on top.
- Name files by purpose: `compose.override.yaml` for dev defaults, `compose.prod.yaml`, `compose.ci.yaml`.
- Use profiles for optional tooling and one-shot jobs, not for core services.
- Always inspect with `docker compose config` and check it in CI for every environment combination.
- Prefer `${VAR:?error}` for required values and `${VAR:-default}` for optional ones.
- Use explicit `-f` in production and automation; rely on the implicit override file only for local development.
- Set `name:` so the project name does not depend on the directory name.
- Use `include:` for team-owned stacks and `extends:` sparingly for service templates.
- Document the supported commands in a Makefile or README (`make dev`, `make prod-config`).

## 10. Common Anti-Patterns / Mistakes

- Copying the whole Compose file per environment (`compose.dev.yaml`, `compose.staging.yaml`, `compose.prod.yaml`, each 200 lines) so they diverge.
- Relying on `compose.override.yaml` being absent on production hosts instead of passing explicit files.
- Giving core services a profile, then wondering why `docker compose up` starts nothing useful.
- Making always-on services depend on profiled services.
- Using profiles to separate security domains, treating them as isolation.
- Putting secrets in `compose.prod.yaml` and committing it.
- Expecting `command:` or `entrypoint:` in an override to append arguments.
- Editing the merged output instead of the sources; `config` output is a diagnostic, not a source file.
- Mixing environment selection into image tags (`web:dev`, `web:prod`) when the same image should be promoted with different config.

## 11. Interview Questions

**🎯 Beginner:** _"What does `profiles: ["debug"]` on a service do, and how do you start it?"_
**Model answer:** A service with a profile is skipped by a plain `docker compose up`; services without profiles always start. You start the profiled service by activating the profile with `docker compose --profile debug up`, by setting `COMPOSE_PROFILES=debug`, or by naming the service directly, for example `docker compose run --rm migrate`, which enables its profile automatically. `docker compose config --profiles` lists the available profile names.
_What the interviewer is probing for:_ That unprofiled services are always on, and the three activation routes.

**🎯 Intermediate:** _"You have `compose.yaml` and `compose.override.yaml`. A teammate adds `ports: ["9090:8000"]` in the override, and now both 8080 and 9090 are published. Why, and what are the fixes?"_
**Model answer:** In the Compose merge rules, sequences such as `ports` are appended, mappings such as `environment` are merged by key, and scalars and `command`/`entrypoint` are replaced. So the override adds a second port mapping. Fixes: use the `!override` YAML tag to replace the list, `!reset` to clear it, or move host ports out of the base file so only the environment files define them. Verify with `docker compose config`.
_What the interviewer is probing for:_ Knowing the merge semantics per attribute type and the newer YAML tags.

**🎯 Senior:** _"How do you make sure a production deploy never picks up developer settings, and how do you test that in CI?"_
**Model answer:** Production never relies on implicit discovery. The deploy script passes `-f compose.yaml -f compose.prod.yaml` explicitly, which suppresses the automatic `compose.override.yaml`, and sets `COMPOSE_PROJECT_NAME`/`name:`. The base file holds only environment-neutral settings; dev bind mounts, `DEBUG`, and debug UIs live in the override or behind a profile. In CI I run `docker compose -f ... config` for each combination, fail on errors, and assert on the rendered output (for example with `yq`) that there are no bind mounts from the source tree, no `privileged`, and only expected published ports. Required variables use `${VAR:?}` so missing configuration fails the render.
_What the interviewer is probing for:_ Defense against configuration drift and leakage, with automated verification rather than convention.

**🎯 Architect:** _"Design a Compose-based setup for 20 microservices owned by different teams, with local dev, CI and a single-node staging environment, without a monolithic 2,000-line file."_
**Model answer:** Each team owns a `compose.yaml` for its service and dependencies, validated standalone. A root `compose.yaml` uses `include:` to compose the teams' files, so paths and env files stay local to each owner and name conflicts surface as errors. Shared service shapes (healthcheck, logging, restart policy) live in an `extends` base or YAML anchors via `x-` extension fields. Environment layers are small deltas: `compose.override.yaml` (bind mounts, debug), `compose.ci.yaml` (no ports, `--wait`, unique `-p` per job), `compose.staging.yaml` (pinned image tags, limits, restart). Optional tooling and migrations use profiles. All combinations are rendered and linted in CI, images are promoted by digest rather than rebuilt per environment, and I document that Compose stops at single-host: beyond staging, the same images move to Swarm or Kubernetes, where I would translate rather than extend the Compose layering.
_What the interviewer is probing for:_ Ownership boundaries, composition versus override, CI validation, immutable promotion, and awareness of Compose's single-host limit.

## 12. Common Misconceptions

- "Profiles isolate services." They only filter which services start; networks are shared and anyone can enable a profile.
- "`compose.override.yaml` is always read." It is read only when you do not pass `-f` (and `COMPOSE_FILE` is unset).
- "An override file can replace the base file." It is merged on top of it; the base must still exist.
- "Lists in an override replace the base list." Most sequences append.
- "Naming a profiled service on the command line fails without the profile." It enables the profile automatically.
- "`extends` and `include` are the same." `extends` reuses one service; `include` imports a whole project model.

## 13. 🔑 Key Takeaways

- Profiles choose which services run; override files change how they are configured.
- No `profiles:` means always on; naming a service explicitly activates its profile.
- Merge rules: scalars replace, mappings merge, sequences append, `command`/`entrypoint` replace; `!override` and `!reset` adjust this.
- Implicit `compose.override.yaml` is for dev; production passes explicit `-f` files.
- Validate every combination with `docker compose config` in CI.
- Do not depend on a profiled service from an unprofiled one.
- Compose layering manages environments on one host; it is not multi-host orchestration.

## 14. Related Concepts & What's Next

Related: file format and merge model ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), services, networks and volumes ([§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), env files and interpolation ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)), `depends_on` ordering ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), CLI behavior ([§40](Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md)), and the dev workflow ([§41](Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md)). Next, [§39](Section-39-Part5-Scaling-Services-with-Compose.md) covers running multiple replicas of a service and the port, DNS and state constraints that come with it.

**Next Section:** [§39](Section-39-Part5-Scaling-Services-with-Compose.md) — `Section-39-Part5-Scaling-Services-with-Compose.md`
