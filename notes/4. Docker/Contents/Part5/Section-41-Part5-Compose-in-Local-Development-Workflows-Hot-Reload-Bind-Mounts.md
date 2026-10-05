# Section 41 (Part 5): Compose in Local Development Workflows: Hot Reload, Bind Mounts

## 1. Definition

**Plain language:** A Compose-based development workflow lets you edit code on your laptop and see it running inside the same containers (same OS, same dependencies, same database) that the rest of the team uses, without rebuilding the image after every keystroke.

**Precise definition:** The inner development loop with Compose combines four mechanisms: (1) **bind mounts** that map host source directories into the container so edits appear instantly; (2) a **file-watching process** inside the container (nodemon, uvicorn `--reload`, Vite, `air`, Spring DevTools) that restarts or hot-swaps the app; (3) **`develop.watch`** (Compose Watch, `docker compose watch` or `up --watch`), which syncs files or rebuilds images based on rules in the Compose file; and (4) **override files** (`compose.override.yaml`) that add these dev-only settings on top of a production-shaped base ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)).

> 💡 **Tip:** `compose.override.yaml` is merged automatically with `compose.yaml` when you run plain `docker compose up`; production deploys name files explicitly with `-f` and skip it.

## 2. Why This Matters

- "Works on my machine" disappears when everyone runs the same containers and the same dependency versions.
- A slow loop (edit, rebuild image, restart) costs minutes per change; a good setup brings it to under a second.
- Wrong mount choices cause the classic problems: `node_modules` overwritten by the host, root-owned files in the repo, slow file I/O on macOS and Windows, and watchers that never fire.
- Dev-only settings (debug ports, reload flags, source mounts) leaking into production images or Compose files are a real security and reliability risk.
- New hires get a working environment with one command (`docker compose up`).

## 3. Prerequisites and Dependencies

Requires Compose basics ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md), [§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), environment handling ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)), ordering ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)), overrides and profiles ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)) and the CLI ([§40](Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md)). Bind mounts versus volumes are covered in depth in [§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md), and mount performance in [§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md). Build stages used for a dev target are in [§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md), and non-root users in [§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md). Compose Watch needs Compose 2.22 or newer (the `sync+restart` action needs 2.23, `sync+exec` 2.32).

## 4. Architecture / Conceptual Diagram

```text
  HOST (laptop)                                  CONTAINER (service "api")
  ┌────────────────────┐   bind mount            ┌──────────────────────────────┐
  │ ~/proj/api/src/    │ ◄──── same files ─────► │ /app/src/                    │
  │   main.py  (edit)  │   (inotify events       │   uvicorn --reload (watcher) │
  └────────────────────┘    propagate on Linux)  │   restarts worker on change  │
                                                 │ /app/.venv  ◄── anonymous vol│
                                                 │   (protects deps from mount) │
                                                 └──────────────────────────────┘

  Three ways to get code changes into a container
  ┌────────────────┬───────────────────┬───────────────────┬────────────────────┐
  │                │ Bind mount        │ develop.watch sync│ develop.watch      │
  │                │ (volumes:)        │ (action: sync)    │ rebuild            │
  ├────────────────┼───────────────────┼───────────────────┼────────────────────┤
  │ Mechanism      │ same dir, live    │ Compose copies    │ new image, new     │
  │                │ view              │ changed files     │ container          │
  │ Speed          │ instant (Linux)   │ fast, copy-based  │ slow (build time)  │
  │ Host-FS I/O    │ slow on Mac/Win  │ native container  │ native container   │
  │                │ for big trees     │ filesystem        │ filesystem         │
  │ Best for       │ interpreted code  │ big trees, Mac/Win│ dependency changes │
  │                │ with a watcher    │ node_modules safe │ (package.json)     │
  └────────────────┴───────────────────┴───────────────────┴────────────────────┘

  File layering
     compose.yaml            (base: image/build, ports, healthchecks, depends_on)
   + compose.override.yaml   (auto-merged in dev: bind mounts, debug, reload command)
   ──────────────────────────
     docker compose up       ► dev stack
     docker compose -f compose.yaml -f compose.prod.yaml up -d   ► production shape
```

- **Bind mount:** a view of a host directory; the container sees edits immediately, and container writes appear on the host.
- **Anonymous or named volume over a subpath:** masks the bind mount for that path, which is how dependency directories are kept inside the container.
- **Watcher inside the container:** the reload logic still lives in the app's tooling; Compose only delivers the files.

## 5. Hands-On

### 5.1 A Dev-Friendly Base: Multi-Stage Dockerfile with a Dev Target

```dockerfile
# api/Dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS dev
RUN pip install --no-cache-dir watchfiles debugpy
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]

FROM base AS prod
COPY . .
RUN useradd -r app && chown -R app /app
USER app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0"]
```

One Dockerfile, two targets: `dev` includes reload tooling, `prod` is lean and non-root.

### 5.2 Base and Override Files

```yaml
# compose.yaml  (shared, production-shaped)
name: shop
services:
  api:
    build:
      context: ./api
      target: prod
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgres://postgres:${DB_PASSWORD:-example}@db:5432/shop
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:-example}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 10
volumes:
  pgdata:
```

```yaml
# compose.override.yaml  (auto-loaded for local work; do not deploy)
services:
  api:
    build:
      target: dev
    volumes:
      - ./api:/app            # source bind mount
      - /app/.venv            # keep container-built deps out of the mount (if used)
    ports:
      - "5678:5678"           # debugpy
    environment:
      APP_ENV: development
      PYTHONUNBUFFERED: "1"
  db:
    ports: ["5432:5432"]      # expose to host tools (psql, DBeaver) in dev only
```

```bash
docker compose up -d
docker compose logs -f api
```

```text
api-1  | INFO:     Will watch for changes in these directories: ['/app']
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000
api-1  | INFO:     Detected file change in 'main.py'. Reloading...
```

After saving `main.py` on the host, the log line shows the reload without any Docker command.

### 5.3 Protecting node_modules (or .venv) from the Mount

A bind mount of the project directory hides everything the image installed under that path. For Node:

```yaml
services:
  web:
    build: { context: ./web, target: dev }
    command: npm run dev -- --host 0.0.0.0
    ports: ["3000:3000"]
    volumes:
      - ./web:/usr/src/app
      - web_node_modules:/usr/src/app/node_modules   # container's copy wins at that path
    environment:
      CHOKIDAR_USEPOLLING: "true"    # only if inotify events do not cross the mount
volumes:
  web_node_modules:
```

The more specific mount (`node_modules`) takes precedence over the parent bind mount. When you change `package.json`, refresh the named volume with `docker compose up -d --build -V` (renew anonymous volumes) or `docker volume rm shop_web_node_modules`.

### 5.4 Compose Watch: sync, rebuild, sync+restart

```yaml
services:
  web:
    build: { context: ./web, target: dev }
    ports: ["3000:3000"]
    develop:
      watch:
        - action: sync                  # copy changed files into the container
          path: ./web/src
          target: /usr/src/app/src
          ignore:
            - "**/*.test.js"
        - action: sync+restart          # copy, then restart the service
          path: ./web/config
          target: /usr/src/app/config
        - action: rebuild               # rebuild image and recreate container
          path: ./web/package.json
```

```bash
docker compose watch
# or run the stack and watch together
docker compose up --watch
```

```text
Watch enabled
 ⠿ Syncing "web" after changes were detected
 ⠿ Rebuilding "web" after changes were detected
```

Rules to remember: `path` is relative to the Compose file; `sync` needs the container to have the target path and a user that can write it; `.dockerignore` patterns apply; and Watch does not mount anything, so code and `node_modules` remain separate and the host-FS performance penalty disappears. Watch pairs well with a dev server's own hot reload, which then reacts to the synced files.

### 5.5 Running Commands Against the Dev Stack

```bash
docker compose exec api pytest -q                    # run tests where the dependencies are
docker compose run --rm api alembic upgrade head     # migrations as a one-off container
docker compose exec db psql -U postgres shop
docker compose run --rm --no-deps api python -m pip list
docker compose exec -u root api sh                   # root only for a debugging session
```

### 5.6 Attaching a Debugger

```yaml
# compose.override.yaml (additional lines)
services:
  api:
    command: ["python", "-m", "debugpy", "--listen", "0.0.0.0:5678",
              "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]
    ports: ["5678:5678"]
```

In VS Code a "Python: Remote Attach" configuration with `host: localhost, port: 5678` and a path mapping from `${workspaceFolder}/api` to `/app` connects to it. Java uses `JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005`, Node uses `node --inspect=0.0.0.0:9229`, and Go uses `dlv` with `--headless`. Publish the debug port to `127.0.0.1` only (see section 7).

### 5.7 Fixing File Ownership

On Linux, a container running as root writes root-owned files into your bind-mounted repository. Run the dev container as your host user:

```yaml
services:
  api:
    user: "${UID:-1000}:${GID:-1000}"
    volumes:
      - ./api:/app
```

```bash
export UID GID=$(id -g)      # bash does not export UID by default
docker compose up -d
```

Alternatively set `USER_UID`/`USER_GID` build args in the dev stage, or use a user-namespace remap ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)). Docker Desktop on macOS and Windows maps ownership automatically.

### 5.8 Dev-Only Services via Profiles

```yaml
services:
  mailpit:
    image: axllent/mailpit
    profiles: ["tools"]
    ports: ["127.0.0.1:8025:8025"]
  adminer:
    image: adminer
    profiles: ["tools"]
    ports: ["127.0.0.1:8081:8080"]
```

```bash
docker compose --profile tools up -d    # app plus helper tools
docker compose up -d                    # app only
```

### 5.9 Resetting to a Clean State

```bash
docker compose down -v --remove-orphans   # wipes DB and cached dependency volumes (dev only)
docker compose build --no-cache api
docker compose up -d
```

Dev stacks should be disposable: seed data scripts mounted into `/docker-entrypoint-initdb.d` (for official database images) recreate a known dataset on the first start of an empty volume.

## 6. Production Usage Notes

- **Separate dev from deploy by file, not by editing.** Deploy with `-f compose.yaml -f compose.prod.yaml`; never ship `compose.override.yaml` and its bind mounts. A production stack running from host source mounts is not reproducible.
- **Build the same Dockerfile with different targets** ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)) so dev and prod share the base layers, differing only in tooling and user.
- **Performance on macOS/Windows:** bind mounts cross a virtualization boundary (virtiofs on Docker Desktop for macOS, WSL2 `9p` when mounting Windows paths into WSL). On Windows, keep the repo inside the WSL2 Linux filesystem (`~/proj`) rather than `/mnt/c`. For huge trees prefer `develop.watch` with `sync`, or exclude heavy folders with volumes ([§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md)).
- **Watcher compatibility:** inotify events normally cross bind mounts on Linux and Docker Desktop; if they do not, use polling flags (`CHOKIDAR_USEPOLLING`, `WATCHFILES_FORCE_POLLING`, `--poll`).
- **Dev tooling fidelity:** run linters and tests inside the containers (`exec`/`run`) so results match CI, and use the same base image tag as production.
- **Reproducibility:** pin image tags in the base file; allow dev overrides only for ports, mounts, commands and debug settings.
- **Resource limits:** Docker Desktop's VM memory and CPU allocation cap everything; a full stack with databases may need 6 to 8 GB.
- **Compose Watch limits:** it syncs one way (host to container), so files generated in the container do not come back; it is not a replacement for a bind mount when you need tools to write to the source tree (code generators, formatters).

## 7. Security Considerations

- **Bind mounts expose host files to the container, and writes affect the host.** A compromised dependency in a dev container can modify your source tree, SSH keys or dotfiles if you mount them; mount only the project directory, and use `:ro` for anything the container does not need to write (configs, certificates, seed data).
- **Never mount the Docker socket, your home directory or cloud credentials** into dev containers casually; for credentials, pass short-lived tokens or use an agent forwarding approach ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Publish dev ports on loopback**: `127.0.0.1:5678:5678`. The bare form `5678:5678` binds `0.0.0.0` and exposes debuggers (which allow remote code execution) and databases to the local network, which matters on shared Wi-Fi.
- **Keep dev defaults out of production:** weak passwords (`example`), debug flags, open database ports and `--reload` commands must live only in the override file. Check what a production deploy would run with `docker compose -f compose.yaml -f compose.prod.yaml config`.
- **Running as root in dev** is convenient but trains bad habits and masks permission bugs; test the real user in at least one environment.
- **`.env` files** hold credentials: add them to `.gitignore` and `.dockerignore`, and commit a `.env.example` with fake values ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)).
- **Untrusted repositories:** a cloned project's `compose.override.yaml` is picked up automatically. Read it before the first `docker compose up`, since it can add privileged mounts.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Changes on host do not appear in the container | Code was copied into the image but no bind mount or watch rule covers it | Add `./src:/app/src` or a `develop.watch` rule |
| App cannot find its dependencies after adding the mount | Bind mount hid `node_modules` / `.venv` / `vendor` | Add a named or anonymous volume at that sub-path |
| Dependency change has no effect | Old `node_modules` volume persists | `up -d --build -V` or remove the volume |
| Reload never triggers | Watcher relies on inotify that is not delivered | Enable polling, or switch to Compose Watch |
| Files in repo owned by root | Container runs as root on Linux | Set `user: "${UID}:${GID}"` |
| `EACCES`/permission denied writing to mounted dir | Container UID differs from host owner | Align UIDs, or `chown` at startup in the entrypoint |
| Very slow tests or installs on macOS/Windows | Large tree on host-mounted filesystem | Use WSL2 filesystem, volumes for deps, or `develop.watch` |
| Port already allocated | Local service or old stack uses the port | `docker compose ps`, change the host port, or `down` |
| Production deploy behaves differently from dev | Override file merged unintentionally | Run production with explicit `-f` list; diff `config` outputs |
| `sync` action does nothing | Path not under the build context, or target not writable | Check `path`, `target`, and container user permissions |
| `docker compose watch` says no `develop` section | Compose version below 2.22, or no rules for the service | Upgrade; add `develop.watch` |
| Windows line endings break shell scripts (`exec format error`) | Git `autocrlf` converted LF to CRLF | Add `.gitattributes` with `*.sh text eol=lf` |

## 9. Best Practices

- Keep `compose.yaml` production-shaped and put dev-only behavior in `compose.override.yaml`.
- Use multi-stage Dockerfiles with `dev` and `prod` targets.
- Mount source narrowly (the `src` directory, not the whole repo with its `.git` and caches) and protect dependency directories with volumes.
- Prefer `develop.watch` on macOS/Windows for big projects; prefer bind mounts for tooling that must write back to the source tree.
- Match container UID/GID to the host user on Linux.
- Bind published dev ports to `127.0.0.1`.
- Add healthchecks and `depends_on: condition: service_healthy` so `up` yields a working stack, not a racing one ([§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)).
- Ship a `.env.example`, seed scripts and a README one-liner (`docker compose up`), and make a reset command (`down -v`) part of the docs.
- Run tests, linters and migrations inside the containers via `run`/`exec`.
- Keep `.dockerignore` current so builds stay fast ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).

## 10. Common Anti-Patterns / Mistakes

- Bind-mounting the whole project over a directory that the image populated (and then wondering why dependencies vanished).
- Running production from bind-mounted source and a dev server.
- Committing a `compose.override.yaml` that works only on one developer's machine (absolute host paths, personal credentials).
- Rebuilding the image on every code change instead of mounting or syncing.
- Running everything as root and committing root-owned files or `chmod -R 777` to "fix" permissions.
- Publishing the database and debugger on all interfaces with default passwords.
- Assuming the dev environment matches production when it uses a different base image, architecture or database version.
- Mounting `~/.ssh`, `~/.aws` or the Docker socket into every dev container by default.
- Treating `docker compose up` on a stale volume as a clean start.
- Using `sleep` loops and ad hoc wait scripts instead of healthchecks.

## 11. Interview Questions

**🎯 Beginner:** _"How do you make code edits on your host show up inside a running container without rebuilding the image?"_
**Model answer:** Bind-mount the source directory into the container with `volumes: - ./src:/app/src` (or `-v` on `docker run`). The container sees the same files as the host, so edits appear immediately. For the running process to pick up changes, the application needs a file watcher or reload mode, such as `uvicorn --reload`, `nodemon` or a Vite dev server. An alternative is Compose Watch (`develop.watch` with `action: sync`), which copies changed files into the container. For production images you do the opposite: copy code into the image with `COPY` and use no bind mounts.
_What the interviewer is probing for:_ Understanding that mounting delivers files while hot reload is an application concern, and that dev and prod differ.

**🎯 Intermediate:** _"After you added `./app:/app` to your Compose file, the container crashes with 'module not found'. The image did `npm ci` during build. What happened and how do you fix it?"_
**Model answer:** The bind mount replaced `/app` in the container with the host directory, hiding the `node_modules` installed in the image layer (and the host may have none, or incompatible native modules built for another OS). Fix it by overlaying a volume at `/app/node_modules`: a named volume or anonymous volume, which is more specific than the bind mount and therefore wins, and is initialized from the image content the first time. After dependency changes, rebuild and renew the volume (`up --build -V` or remove the volume). Alternatively use `develop.watch` with `sync` on `src` only and `rebuild` on `package.json`, which avoids mounting the parent directory at all.
_What the interviewer is probing for:_ Mount precedence and masking semantics, and awareness of the host versus container dependency problem.

**🎯 Senior:** _"Developers on macOS report that the Compose dev stack is five times slower than on Linux. Tests and file watching lag. What are the causes and your options?"_
**Model answer:** On macOS and Windows, Docker runs in a Linux VM, and bind mounts cross a file-sharing layer (virtiofs, gRPC-FUSE or 9p) with per-operation overhead, which hurts directories with many small files such as `node_modules`, `.git` or build caches; inotify events may also be delayed or missing. Options in order: move dependency and cache directories into named volumes; on Windows put the repository inside the WSL2 filesystem; use Compose Watch with `sync` so files are copied into the container's native filesystem; mount only `src`; enable the faster file-sharing implementation in Docker Desktop settings; use polling only as a last resort because it burns CPU. If the tooling needs write-back, keep a narrow bind mount for it. Measure with a repeatable test run before and after each change.
_What the interviewer is probing for:_ Knowledge of why mounts are slow on VM-based Docker and a prioritized, measured response.

**🎯 Architect:** _"Design the local-development story for 30 engineers across four services plus Postgres, Redis and a message broker, on mixed Linux, macOS and Windows machines, so that dev stays close to production and onboarding takes minutes."_
**Model answer:** One repo-level `compose.yaml` that mirrors production service definitions (same Dockerfile, pinned versions of Postgres, Redis and the broker, healthchecks, `depends_on` with health conditions), plus a `compose.override.yaml` for dev: `dev` build targets, watch rules, debug ports on loopback, helper tools under a `tools` profile. Per-service `develop.watch` for cross-platform speed, with bind mounts only where write-back is required. A `.env.example`, seed and migration jobs as `run --rm` services under a `setup` profile, and a Makefile or task runner wrapping `up`, `reset`, `test`. Enforce consistency in CI by running `docker compose config` for dev and prod combinations, building the `prod` target, and running integration tests with `up --abort-on-container-exit --exit-code-from` ([§83](../Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)). Document resource needs, and for stacks too large for laptops, point to profiles that start subsets or a remote Docker context. State the boundary clearly: Compose is the dev and test contract, while production orchestration (Kubernetes or similar) consumes the same images, not the same Compose file ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).
_What the interviewer is probing for:_ Developer experience engineering: parity with production, cross-platform performance, onboarding automation and guardrails.

## 12. Common Misconceptions

- "A bind mount makes the app reload." It only delivers files; the process needs a watcher.
- "`compose.override.yaml` is a dev-only file the tool ignores in production." It is merged automatically by any plain `docker compose` command run in that directory.
- "Compose Watch replaces bind mounts." It copies files one way and suits different cases; bind mounts remain right for write-back tools.
- "Dev containers should run as root for convenience." That hides permission bugs and pollutes the host tree on Linux.
- "Docker Desktop makes mounts as fast as native." Large-tree I/O still has overhead.
- "If it works in my Compose dev stack, it will work in production." Different targets, users, mounts and limits can diverge.

## 13. 🔑 Key Takeaways

- Bind mounts or `develop.watch` deliver code; an in-container watcher reloads it.
- Layer dev settings in `compose.override.yaml` and deploy with an explicit `-f` list.
- Overlay a volume on dependency directories to stop the mount from hiding them.
- Use `dev` and `prod` build targets from a single Dockerfile.
- Publish dev ports on `127.0.0.1`, mount narrowly, and use `:ro` where possible.
- Align UID/GID on Linux; keep repos on the WSL2 filesystem on Windows.
- Use `exec`/`run --rm` to run tests and migrations inside the containers.
- Keep dev stacks disposable with seed data and a documented reset.

## 14. Related Concepts & What's Next

Related: Compose CLI ([§40](Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md)), overrides and profiles ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)), environment files ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)), bind mounts versus volumes ([§51](../Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)), storage performance ([§56](../Part7/Section-56-Part7-Storage-Performance-Considerations.md)), multi-stage builds ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)) and integration testing with ephemeral containers ([§83](../Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)). Part 5 ends here. Next, Part 6 begins with [§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md), which looks beneath the default Compose network at Docker's network drivers: bridge, host, none, overlay and macvlan.

**Next Section:** [§42](../Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md) — `Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md`
