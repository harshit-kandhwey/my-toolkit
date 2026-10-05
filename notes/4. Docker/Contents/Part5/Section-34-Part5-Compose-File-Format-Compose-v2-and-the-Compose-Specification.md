# Section 34 (Part 5): Compose File Format: Compose v2 and the Compose Specification

## 1. Definition

**Plain language:** Docker Compose lets you describe a whole multi-container application (containers, networks, volumes, settings) in one YAML file and start or stop all of it with a single command. The file is the written-down version of a long list of `docker run` flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)).

**Precise definition:** The **Compose Specification** is an open, vendor-neutral specification (maintained at compose-spec.io) for the file format. **Compose v2** is the implementation: a Go rewrite shipped as a Docker CLI plugin, invoked as `docker compose` (space, not hyphen). It replaced the Python `docker-compose` v1 binary, which reached end of life in 2023 and is no longer shipped. The Compose Specification merged the older 2.x and 3.x file-format lines into one schema, so the top-level `version:` key is **obsolete**: Compose v2 ignores it and prints a warning. The specification defines these top-level elements:

| Element | Purpose |
|---|---|
| `name` | Project name (optional; otherwise derived from the directory) |
| `services` | The containers to run (required) |
| `networks` | Networks services attach to |
| `volumes` | Named volumes |
| `configs` | Non-secret configuration files mounted into services |
| `secrets` | Sensitive files mounted into services ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)) |
| `include` | Pull in other Compose files as sub-applications |
| `x-*` | Extension fields: ignored by Compose, used for reusable YAML fragments |

The canonical file name is `compose.yaml` (preferred) or `compose.yml`. Compose also still accepts `docker-compose.yaml` and `docker-compose.yml` for backward compatibility; if several exist in a directory, `compose.yaml` wins.

> 💡 **Tip:** If a tutorial says `docker-compose up` and starts with `version: "3.8"`, it predates the unified specification. Translate it: use `docker compose up`, delete the `version:` line, and the file generally works unchanged.

## 2. Why This Matters

- A multi-container stack described as shell scripts of `docker run` flags drifts, breaks on a teammate's machine, and cannot be reviewed in a pull request. A Compose file is declarative, diffable and versionable.
- Compose is the de facto format for local development, integration tests in CI ([§83](../Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)), and small single-host deployments.
- Confusion between v1, v2, the `version:` key and the specification is the number one source of copy-paste errors from old blog posts.
- Knowing merge, interpolation and validation rules is what lets you build overrides ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)) without surprises.
- It is a common interview and DCA-adjacent topic ([§100](../Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)).

## 3. Prerequisites and Dependencies

You need a working Docker Engine or Docker Desktop with the Compose plugin ([§4](../Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)); confirm with `docker compose version`. You should know `docker run` flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), images and Dockerfiles ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), and basic YAML (indentation, lists, maps, anchors). Compose talks to the daemon through the REST API ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)), so it needs access to the same socket as the `docker` CLI. The detailed contents of `services`, `networks` and `volumes` are the subject of [§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md).

## 4. Architecture / Conceptual Diagram

```text
  compose.yaml ──┐
  compose.override.yaml ──┤  (merged in order)        .env / shell env
  -f extra.yaml ─────────┘                                  │
                │                                           ▼
                ▼                                   ┌───────────────┐
        ┌──────────────┐   interpolation ${VAR}     │  variables    │
        │ raw YAML     │ ◄──────────────────────────│  (see §36)    │
        └──────┬───────┘                            └───────────────┘
               │ parse + merge + validate against the Compose Specification
               ▼
        ┌──────────────────────────┐
        │ canonical project model  │   ◄── `docker compose config` prints this
        │  name, services, nets,   │
        │  volumes, configs, ...   │
        └──────┬───────────────────┘
               │ Compose v2 (Go, CLI plugin) translates model into API calls
               ▼
        ┌──────────────────────────┐        ┌──────────────────────────┐
        │ dockerd REST API         │ ─────► │ containers, networks,    │
        │ (+ BuildKit for build:)  │        │ volumes labeled with     │
        └──────────────────────────┘        │ com.docker.compose.*     │
                                            └──────────────────────────┘
```

- **Project:** the unit Compose manages. Its name (from `name:`, `-p`, `COMPOSE_PROJECT_NAME`, or the directory name) prefixes every resource it creates, such as `myapp-web-1` and `myapp_default`.
- **Labels, not a state file:** Compose records ownership as labels (`com.docker.compose.project`, `.service`, `.config-hash`) on the Docker objects. There is no hidden database; Compose rediscovers state by querying the daemon.
- **Config hash:** if a service's resolved configuration changes, `up` recreates just that container; unchanged services are left alone.

## 5. Hands-On

### 5.1 A Minimal Specification-Style File

```yaml
# compose.yaml  (no "version:" key)
name: demo
services:
  web:
    image: nginx:1.27-alpine
    ports:
      - "8080:80"
  cache:
    image: redis:7-alpine
```

```bash
docker compose version
docker compose up -d
docker compose ps
```

```text
Docker Compose version v2.29.7
 Container demo-cache-1  Started
 Container demo-web-1    Started
NAME           IMAGE               COMMAND                  SERVICE   STATUS         PORTS
demo-cache-1   redis:7-alpine      "docker-entrypoint.s…"   cache     Up 2 seconds   6379/tcp
demo-web-1     nginx:1.27-alpine   "/docker-entrypoint.…"   web       Up 2 seconds   0.0.0.0:8080->80/tcp
```

### 5.2 Validate and Print the Resolved Model

```bash
docker compose config            # validate, interpolate, merge; print canonical YAML
docker compose config -q         # validate only; exit code 0/1 (good CI gate)
docker compose config --services # list service names
```

`config` is the single most useful command for this section: it shows what Compose actually understood after merging files and substituting variables. Note that it expands short syntax into long syntax (for example, `"8080:80"` becomes a `target`/`published`/`protocol` mapping).

### 5.3 Short Syntax vs Long Syntax

Many attributes accept both forms. They are equivalent; long syntax is explicit and exposes more options.

```yaml
services:
  web:
    image: nginx:1.27-alpine
    ports:
      - "8080:80"                 # short
      - target: 443               # long
        published: "8443"
        protocol: tcp
        host_ip: 127.0.0.1
    volumes:
      - ./site:/usr/share/nginx/html:ro   # short
      - type: bind                        # long
        source: ./conf
        target: /etc/nginx/conf.d
        read_only: true
```

### 5.4 Reusable Fragments: Anchors and Extension Fields

```yaml
x-common: &common
  restart: unless-stopped
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"

services:
  api:
    <<: *common
    image: ghcr.io/example/api:1.4.2
  worker:
    <<: *common
    image: ghcr.io/example/worker:1.4.2
```

The `x-` prefix tells Compose to ignore the block, while the YAML anchor (`&common`) and merge key (`<<: *common`) are resolved by the YAML parser before Compose sees the model. Anchors work only within one file; they do not cross `-f` files or `include`.

### 5.5 Multiple Files and Merge Rules

```yaml
# compose.yaml
services:
  web:
    image: nginx:1.27-alpine
    ports: ["8080:80"]
    environment:
      LOG_LEVEL: info
```

```yaml
# compose.override.yaml  (picked up automatically)
services:
  web:
    ports: ["9090:80"]
    environment:
      LOG_LEVEL: debug
      DEBUG: "1"
```

```bash
docker compose config
docker compose -f compose.yaml -f prod.yaml config     # explicit list, skips the override file
```

```text
services:
  web:
    environment:
      DEBUG: "1"
      LOG_LEVEL: debug
    image: nginx:1.27-alpine
    networks:
      default: null
    ports:
      - mode: ingress
        target: 80
        published: "8080"
        protocol: tcp
      - mode: ingress
        target: 80
        published: "9090"
        protocol: tcp
```

Merge rules in short: single-value fields (`image`, `command`) are **replaced** by the later file; maps (`environment`, `labels`) are merged key by key; lists such as `ports`, `expose`, `dns` and `volumes` are **appended** (hence two published ports above). Use the `!reset` tag to clear a value or `!override` to replace a list instead of appending (supported in current Compose v2).

```yaml
services:
  web:
    ports: !override
      - "9090:80"
```

### 5.6 Project Name Resolution

```bash
docker compose -p staging up -d         # highest priority: -p flag
COMPOSE_PROJECT_NAME=ci docker compose up -d
docker compose ls                        # all projects on this daemon
```

Priority order: `-p` flag, then `COMPOSE_PROJECT_NAME`, then top-level `name:`, then the directory name of the first Compose file. Project names must be lowercase letters, digits, dashes and underscores, and begin with a letter or digit.

### 5.7 `include` and `extends`

```yaml
# compose.yaml
include:
  - path: ./observability/compose.yaml
  - path: ../shared/db.yaml
    env_file: ./db.env
services:
  app:
    image: ghcr.io/example/app:2.0.0
    extends:
      file: ./common.yaml
      service: base-service
```

`include` loads another Compose file as a self-contained sub-model with its **own** relative paths and project-directory resolution, and fails on conflicting resource names. It suits teams that own separate stacks. `extends` copies one service definition from another (or the same) file and lets you override parts, but it does not copy `depends_on` relationships or volumes_from. For simple cases, plain `-f` merging or anchors is easier.

### 5.8 Interpolation Syntax

```yaml
services:
  api:
    image: "ghcr.io/example/api:${TAG:-latest}"
    environment:
      DB_URL: "postgres://app:${DB_PASS:?DB_PASS must be set}@db:5432/app"
```

`${VAR}`, `${VAR:-default}` (default if unset or empty), `${VAR-default}` (default only if unset), `${VAR:?error}` (abort if unset or empty) and `$$` (a literal dollar sign). Where variables come from is covered in [§36](Section-36-Part5-Environment-Variables-and-env-Files.md).

### 5.9 Watching for Obsolete or Wrong Keys

```bash
docker compose -f old-v3.yaml config
```

```text
WARN[0000] old-v3.yaml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion
```

Unknown keys under a service are rejected (`additional properties 'foo' not allowed`), which is why `config -q` catches typos before anything starts.

## 6. Production Usage Notes

- **Name the file `compose.yaml`** and omit `version:`. Pin `image:` tags (never `latest`) so `config` output is reproducible.
- **Keep one base file plus thin overrides** rather than copies of the whole file per environment ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)).
- **Gate CI** with `docker compose config -q` so a malformed or incomplete file never reaches a deploy step.
- **Compose is a single-host tool.** It plans and applies against one Docker daemon. For multi-host clustering see Swarm ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)) or Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).
- **`deploy:` keys** (`replicas`, `resources.limits`) are part of the specification and are honored by Compose v2 for replicas and resource limits; Swarm-only keys such as `placement` or `update_config` are ignored outside Swarm.
- **Remote contexts:** `docker --context prod compose up -d` applies the same file against a remote engine over SSH; project names still scope the resources.
- **Compose Bridge and Compose-to-Kubernetes converters** exist, but treat a Compose file as the source of truth only for the Docker-host use case.
- Check compatibility: Docker Desktop and recent Docker Engine packages bundle Compose v2; on a minimal Linux server install `docker-compose-plugin` from the Docker repository.

## 7. Security Considerations

- **Interpolation leaks into the model.** `docker compose config` prints resolved values, including passwords taken from the environment. Never paste its output into tickets or CI logs without redaction.
- **Do not commit `.env` files with real secrets**, and do not hard-code credentials in `environment:`. Use `secrets:` with file sources, or an external secret manager ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- **A Compose file is executable infrastructure.** `privileged: true`, `network_mode: host`, `pid: host`, and bind-mounting `/var/run/docker.sock` or `/` grant host-level control ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)). Review them in pull requests like code.
- **Untrusted files:** running `docker compose up` on a file from an unknown source is equivalent to running its commands with your Docker privileges. Inspect `config` output first.
- **Remote includes** (`include` with an `oci://` or git URL) pull configuration from outside your repository; pin to a digest or tag and review it.
- **Published ports default to all interfaces** (`0.0.0.0`). Bind to `127.0.0.1:` for local-only services.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `docker: 'compose' is not a docker command` | Plugin not installed | Install `docker-compose-plugin` or use Docker Desktop |
| `docker-compose: command not found` | Only v2 installed | Use `docker compose` (space) |
| Warning: attribute `version` is obsolete | Legacy header | Delete the `version:` line |
| `additional properties 'x' not allowed` | Typo or key in the wrong place | `docker compose config` and fix indentation or key name |
| `yaml: line N: mapping values are not allowed` | Tabs or bad indentation | Use two spaces, never tabs |
| Port or variable shows as blank | Unset variable resolved to empty string | Use `${VAR:?msg}`; check with `config` |
| Override file ignored | Used `-f` explicitly (disables auto-override) | List both files or drop `-f` |
| Wrong project or duplicate stacks | Directory name differs between machines | Set `name:` in the file |
| List value got duplicated after merge | Lists are appended by default | Use `!override` or restructure |
| `service "x" refers to undefined network/volume` | Used but not declared at top level | Add it under `networks:` or `volumes:` |

## 9. Best Practices

- Use `compose.yaml`, no `version:`, and an explicit top-level `name:`.
- Prefer long syntax when options matter (`ports`, `volumes`, `depends_on`); it is self-documenting.
- Run `docker compose config -q` in pre-commit hooks and CI.
- Use extension fields and anchors for repeated blocks (logging, restart policy, resource limits).
- Pin image tags or digests ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- Keep the base file environment-neutral; put differences in overrides or profiles ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)).
- Quote port mappings and variable-like strings (`"8080:80"`, `"1"`, `"yes"`) so YAML does not coerce them (sexagesimal numbers and booleans).
- Commit the Compose file next to the Dockerfile and `.dockerignore` so the application and its runtime topology version together.

## 10. Common Anti-Patterns / Mistakes

- Starting every file with `version: "3.8"` out of habit.
- Typing `docker-compose` and mixing v1 behaviour assumptions (v1 stored container names with underscores; v2 uses hyphens, for example `proj-web-1`).
- Using `container_name:` everywhere. It prevents scaling ([§39](Section-39-Part5-Scaling-Services-with-Compose.md)) and causes name collisions between projects.
- Copy-pasting the entire file for dev, staging and prod instead of overriding.
- Using `links:`; it is legacy. Services on a shared network already resolve each other by name ([§44](../Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)).
- Depending on YAML anchors across files (they do not cross file boundaries).
- Treating `latest` tags as a stable default.
- Editing running containers by hand instead of changing the file and re-running `up`.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `docker-compose` and `docker compose`, and do you still need a `version:` key?"_
**Model answer:** `docker-compose` was the Python v1 standalone tool, now end of life. `docker compose` is Compose v2, a Go plugin of the Docker CLI that implements the Compose Specification. The specification merged the older 2.x and 3.x formats into one schema, so `version:` is obsolete; v2 ignores it and warns. The recommended file name is `compose.yaml`. Resources are named with hyphens (`project-service-1`) in v2 rather than underscores.
_What the interviewer is probing for:_ Awareness that tooling and format changed, and that the candidate does not rely on stale tutorials.

**🎯 Intermediate:** _"You have `compose.yaml` and `compose.override.yaml`; both define `ports` and `environment` for a service. What does the merged result look like, and how do you check it?"_
**Model answer:** Compose merges files in order. Mapping fields such as `environment` merge by key with later values winning; sequence fields such as `ports` are concatenated, so both port mappings end up published (and may collide); scalars like `image` are replaced. `docker compose config` prints the merged, interpolated model. To replace a list rather than append, use the `!override` tag, and to remove an inherited value use `!reset`. Passing `-f` explicitly disables auto-loading of the override file.
_What the interviewer is probing for:_ Understanding merge semantics and using `config` to verify instead of guessing.

**🎯 Senior:** _"Two teams own separate stacks (platform observability and an app). How do you compose them without duplicating YAML, and what are the pitfalls of `extends`, `include` and `-f` merging?"_
**Model answer:** `include` embeds another Compose file as a self-contained sub-project: its relative paths resolve against its own location, and a resource-name conflict is an error, which suits independently owned stacks. `-f` merging overlays files that share one namespace and one working directory, good for environment overrides but prone to implicit coupling and appended lists. `extends` reuses a single service definition but does not bring `depends_on` or volume sharing and is the least maintainable. YAML anchors only work within one file. I would use `include` for team boundaries, `-f` for environment deltas, and anchors/`x-` fields for repeated blocks, with `config -q` in CI to catch conflicts.
_What the interviewer is probing for:_ Choosing the right reuse mechanism and knowing each one's scoping rules.

**🎯 Architect:** _"Leadership asks whether the Compose file can be the production deployment artifact for 40 services. How do you answer?"_
**Model answer:** The Compose Specification is portable and fine as the single-host description, including remote contexts and `deploy.replicas`, but Compose has no scheduler, no cross-host networking, no rolling-update controller with automatic rollback, and no node failure handling. For a handful of services on one VM with an external load balancer it is acceptable; for 40 services with availability targets I would use an orchestrator ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)). The Compose file still pays off as the developer-environment and CI-integration definition, and can seed conversion to Kubernetes manifests, but I would not let the two diverge silently; I would define a promotion path and test both.
_What the interviewer is probing for:_ Honest scoping of Compose's role and ability to articulate when to move to an orchestrator.

## 12. Common Misconceptions

- "Compose v2 files need `version: '3'`." The key is obsolete and ignored.
- "`docker-compose` and `docker compose` are the same binary." They are different implementations.
- "Compose is only for development." It also serves CI and small single-host deployments, with limits.
- "`.yaml` and `.yml` file names behave differently." Both are accepted; `compose.yaml` is preferred.
- "YAML anchors are a Compose feature." They are plain YAML, resolved before Compose reads the model.
- "`docker compose config` just echoes the file." It merges, interpolates, validates and normalizes.
- "Compose stores state in a hidden file." State lives in labels on Docker objects.

## 13. 🔑 Key Takeaways

- Compose Specification = the format; Compose v2 = `docker compose`, the implementation. v1 is end of life.
- Use `compose.yaml`; drop `version:`; set `name:`.
- Top-level elements: `services`, `networks`, `volumes`, `configs`, `secrets`, `include`, `name`, `x-*`.
- Merge: scalars replace, maps merge, lists append; `!override` and `!reset` adjust it.
- `docker compose config` shows the true resolved model; `config -q` is a CI gate.
- Compose manages one project on one daemon and tracks objects via labels.
- A Compose file is infrastructure code: review it and keep secrets out of it.

## 14. Related Concepts & What's Next

Related: `docker run` flags that map onto service keys ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), the REST API Compose calls ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)), tagging ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), and the build step used by `build:` ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)). Later parts build on it: variables ([§36](Section-36-Part5-Environment-Variables-and-env-Files.md)), profiles and overrides ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)), and the CLI ([§40](Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md)). Next, [§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md) goes inside the three core elements: services, networks and volumes.

**Next Section:** [§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md) — `Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md`
