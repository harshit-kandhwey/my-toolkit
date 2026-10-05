# Section 36 (Part 5): Environment Variables and .env Files

## 1. Definition

**Plain language:** Compose lets you keep configuration out of the YAML. Values live in your shell, in a `.env` file, or in `env_file` files, and are pulled into the Compose file (**interpolation**) or injected into containers (**container environment**). These are two different jobs that people constantly confuse.

**Precise definition:** Compose v2 has two separate mechanisms:

1. **Interpolation (substitution) in the Compose file.** `${VAR}` expressions inside `compose.yaml` are resolved *by the Compose CLI* before the model is sent to the engine. Sources, highest precedence first: the shell environment of the `docker compose` process, then files named with `--env-file`, then the project-directory `.env` file. A variable that is unset everywhere becomes an empty string (with a warning) unless you give a default or a required-check.
2. **Container environment.** What the process inside the container sees. It is built from the service's `environment:` and `env_file:` attributes (plus the image's `ENV`). A variable is **not** passed to a container merely because it exists in `.env`.

The default `.env` is read from the **project directory** (the directory of the first Compose file, or `--project-directory`), not from the current working directory if they differ. Passing `--env-file` replaces that default `.env` rather than adding to it.

> 💡 **Tip:** Run `docker compose config` before `up`. It prints the fully interpolated model, which is the ground truth for what Compose will actually deploy.

## 2. Why This Matters

- The same Compose file must run on a laptop, in CI and on a staging host with different ports, image tags and credentials.
- Confusing interpolation with container environment is the most common Compose bug: "I put it in `.env` but the app does not see it."
- Precedence rules decide which value wins when a variable is defined in three places; getting it wrong ships the wrong database URL.
- Plain environment variables are visible in `docker inspect` and `/proc`, so how you inject values is a security decision ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- Frequent interview topic because the two mechanisms and the precedence order are easy to blur.

## 3. Prerequisites and Dependencies

Needs the Compose file basics ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)) and the service model ([§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)). The image-side counterparts, `ENV` and `ARG`, are in [§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md); `docker run -e/--env-file` is in [§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md). Profiles and multi-file overrides, which also use variables, are in [§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md).

## 4. Architecture / Conceptual Diagram

```text
  INTERPOLATION (CLI side, before anything reaches the engine)

   shell env  ──┐   highest
   --env-file ──┼──► resolve ${VAR} in compose.yaml ──► resolved model
   ./.env     ──┘   lowest                              (docker compose config)
                                                              │
                                                              ▼
  CONTAINER ENVIRONMENT (what the process sees), highest first

   docker compose run -e VAR=x                      ◄── 1 (run only)
   environment:  (value or ${VAR} resolved above)   ◄── 2
   env_file:     (later files override earlier)     ◄── 3
   image ENV (Dockerfile)                           ◄── 4

  Not automatic:   .env  ──X──►  container
  Only reaches the container if environment:/env_file: names it.
```

- **`.env` is an input to Compose, not to containers.** It feeds `${...}` substitution and `COMPOSE_*` settings.
- **`environment:` beats `env_file:`.** An explicit key in the YAML overrides the same key from a file.
- **Shell beats `.env`.** A stale `export DB_PASSWORD=...` in your terminal silently overrides the file.

## 5. Hands-On

### 5.1 Interpolation From `.env`

```yaml
# compose.yaml
services:
  web:
    image: nginx:${NGINX_TAG:-1.27-alpine}
    ports:
      - "${WEB_PORT:-8080}:80"
```

```bash
# .env  (same directory as compose.yaml)
NGINX_TAG=1.27.2-alpine
WEB_PORT=9090
```

```bash
docker compose config
```

```text
services:
  web:
    image: nginx:1.27.2-alpine
    ports:
      - mode: ingress
        target: 80
        published: "9090"
        protocol: tcp
```

Delete `.env` and the defaults (`1.27-alpine`, `8080`) apply.

### 5.2 Interpolation Syntax

| Form | Meaning |
|---|---|
| `${VAR}` / `$VAR` | Value, or empty string (with a warning) if unset |
| `${VAR:-default}` | `default` if unset **or empty** |
| `${VAR-default}` | `default` only if unset (empty counts as set) |
| `${VAR:?error msg}` | Abort with `error msg` if unset or empty |
| `${VAR?error msg}` | Abort only if unset |
| `${VAR:+alt}` | `alt` if set and non-empty, else empty |
| `$$` | A literal `$` (no interpolation) |

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD must be set}
      PGDATA: /var/lib/postgresql/data/pgdata
  app:
    image: myapp:${TAG:-dev}
    command: ["sh", "-c", "echo cost is $$5"]   # $$ keeps a literal $ for the container shell
```

```bash
docker compose config
```

```text
error while interpolating services.db.environment.POSTGRES_PASSWORD:
required variable DB_PASSWORD is missing a value: DB_PASSWORD must be set
```

### 5.3 The Container Only Sees What You Pass

Map form and list form are equivalent:

```yaml
services:
  app:
    image: alpine:3.20
    command: ["env"]
    environment:                    # map form
      LOG_LEVEL: debug
      API_URL: ${API_URL}
      PASS_THROUGH:                 # null value: take it from the shell, unset if absent
```

```yaml
    environment:                    # list form
      - LOG_LEVEL=debug
      - API_URL=${API_URL}
      - PASS_THROUGH                # bare name: copy from the shell
```

```bash
# .env contains SECRET_TOKEN=abc, but nothing references it
docker compose run --rm app
```

```text
LOG_LEVEL=debug
API_URL=https://api.example.test
PATH=/usr/local/sbin:...
HOSTNAME=3f2c9a1b7d10
HOME=/root
```

`SECRET_TOKEN` is absent because no `environment:` or `env_file:` entry names it.

### 5.4 `env_file` for Container Environment

```yaml
services:
  app:
    image: alpine:3.20
    command: ["env"]
    env_file:
      - ./common.env
      - path: ./local.env      # Compose 2.24+: long syntax
        required: false        # do not fail if the file is missing
    environment:
      LOG_LEVEL: warn          # beats LOG_LEVEL in either file
```

```bash
# common.env
LOG_LEVEL=info
DB_HOST=db
# local.env
LOG_LEVEL=debug
DB_HOST=localhost
```

```text
LOG_LEVEL=warn
DB_HOST=localhost
```

Files are read in order, so `local.env` overrides `common.env`, and `environment:` overrides both.

### 5.5 `.env` File Syntax

```bash
# comment line
PLAIN=value
SPACED="two words"            # double quotes: \n \t escapes and ${OTHER} expansion
LITERAL='no $expansion here'  # single quotes: taken literally
EMPTY=
INLINE=value # trailing comment (needs a space before #)
export FROM_SHELL_STYLE=ok    # a leading export is tolerated
URL=http://${HOST:-localhost}:${PORT:-80}   # reference earlier variables, with defaults
```

Keep files LF-terminated. A stray carriage return from CRLF checkouts can end up inside a value and produce confusing failures.

### 5.6 Selecting a Different Env File and Precedence in Practice

```bash
docker compose --env-file ./env/prod.env config | grep image
WEB_PORT=7000 docker compose config | grep published
docker compose --env-file base.env --env-file prod.env config   # later file wins
```

```text
    image: nginx:1.27.2-alpine
        published: "7000"
```

The shell assignment `WEB_PORT=7000` beats any `.env` or `--env-file` value.

### 5.7 Build Arguments and Compose Settings

```yaml
services:
  app:
    build:
      context: .
      args:
        APP_VERSION: ${APP_VERSION:-dev}   # interpolation feeds the Dockerfile ARG
```

```bash
# .env can also set Compose's own behavior
COMPOSE_PROJECT_NAME=shop
COMPOSE_PROFILES=dev
COMPOSE_FILE=compose.yaml:compose.dev.yaml
```

### 5.8 Verifying What the Container Received

```bash
docker compose up -d
docker compose exec app env | sort
docker inspect "$(docker compose ps -q app)" --format '{{json .Config.Env}}'
docker compose config --variables      # lists variables the file references and their defaults
```

## 6. Production Usage Notes

- **Commit `.env.example`, ignore `.env`.** The example file documents every variable; the real one holds local or secret values and stays out of Git.
- **One Compose file, several env files.** Select with `--env-file prod.env` (or `COMPOSE_ENV_FILES`) in CI rather than editing YAML.
- **Use `:?` for mandatory values** so a missing variable fails at `config` time instead of starting a database with an empty password.
- **Pin image tags through variables** (`image: app:${TAG:?}`), set by CI to the commit SHA, so deploys are traceable ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- **Prefer secrets for credentials.** Compose supports top-level `secrets:` mounted at `/run/secrets/<name>`; many official images accept `*_FILE` variants (for example `POSTGRES_PASSWORD_FILE`).
- **Know the shell wins.** CI runners often export variables; local shells accumulate stale ones. Print `docker compose config` in pipeline logs (with secrets masked) to see the resolved values.
- **Do not rely on `.env` for the production runtime.** It configures the Compose CLI; the running container has only what was injected at creation time. Changing a value requires `docker compose up -d` to recreate the container.

## 7. Security Considerations

- **Environment variables are readable.** They appear in `docker inspect`, `docker compose config`, `/proc/<pid>/environ` and often in crash dumps and debug endpoints.
- **`docker compose config` prints resolved secrets.** Never paste its output into tickets or CI logs unfiltered.
- **Never commit `.env`.** Add it to `.gitignore` and `.dockerignore` ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)) so it is not copied into images by `COPY . .`.
- **Do not put secrets in `build.args`.** Build args persist in image history; use BuildKit secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Interpolating untrusted values** into `command:` strings that run through a shell can inject arguments; prefer exec-form lists.
- **Least exposure.** Give each service only the variables it needs; a shared `env_file` handed to every service widens the blast radius.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| App cannot see a variable defined in `.env` | `.env` only feeds interpolation | Add it under `environment:` or `env_file:` |
| Value differs from `.env` | Stale variable exported in the shell | `unset VAR`, or check with `docker compose config` |
| `WARN The "X" variable is not set. Defaulting to a blank string.` | Variable missing from all sources | Add to `.env`, give a default, or use `:?` |
| `.env` ignored | Running from another directory, or `--env-file` given | Use `--project-directory`, or pass the intended file |
| Literal `$` mangled in `command:` | Compose interpolated it | Write `$$` |
| Changed `.env`, container unchanged | Env is fixed at container creation | `docker compose up -d` to recreate |
| Quotes appear inside the value | Quoting rules differ between `.env` and shell | Use `docker compose config` to inspect; quote per `.env` rules |
| Error on missing `env_file` | File does not exist | Create it or use `required: false` |
| Value ends with an odd trailing character | CRLF line endings | Convert to LF, add `.gitattributes` `eol=lf` |

## 9. Best Practices

- Treat `.env` as Compose configuration and `environment:`/`env_file:` as the app's configuration.
- Always provide defaults (`:-`) for optional values and `:?` for required ones.
- Keep a documented `.env.example` in the repo.
- Name variables by owner (`DB_`, `REDIS_`, `APP_`) to avoid collisions across services.
- Run `docker compose config` in CI as a lint step.
- Use secrets or `*_FILE` variables for credentials in anything beyond local development.
- Keep one source of truth per value; do not define the same key in `.env`, `env_file` and `environment:` unless the override is intentional and commented.

## 10. Common Anti-Patterns / Mistakes

- Expecting every variable in `.env` to appear in the container.
- Committing real credentials in `.env` or in `environment:` literals.
- Using `env_file: .env` for every service, exposing unrelated secrets to all of them.
- Using `${VAR}` in `command:` when the container shell was meant to expand it at run time (needs `$$VAR`).
- Depending on an exported shell variable that CI does not have.
- Editing a running container's environment with `docker exec` and expecting it to persist.
- Using variables for structure (service names, whole blocks) instead of profiles and overrides ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)).

## 11. Interview Questions

**🎯 Beginner:** _"You have `DB_HOST=db` in `.env`, and your app reads `DB_HOST`, but it is empty inside the container. Why?"_
**Model answer:** The `.env` file is read by the Compose CLI to resolve `${...}` expressions in the Compose file; it is not automatically injected into containers. To expose the value, either reference it under `environment:` (for example `DB_HOST: ${DB_HOST}`), list `DB_HOST` as a pass-through, or point `env_file:` at a file containing it. I would confirm with `docker compose config` to see the resolved model and `docker compose exec app env` to see what the process receives.
_What the interviewer is probing for:_ Knowing interpolation and container environment are separate mechanisms.

**🎯 Intermediate:** _"The same variable is set in the shell, `.env`, an `env_file` and `environment:`. Which value does the container get, and which does `${VAR}` in the YAML get?"_
**Model answer:** Interpolation in the YAML uses shell first, then `--env-file`, then `.env`. The container's environment is separate: `docker compose run -e` wins, then `environment:` (after its own interpolation), then `env_file:` entries (later files override earlier), then the image's `ENV`. So the container normally gets the `environment:` value, which itself may have been interpolated from the shell. I would avoid defining one key in four places, and I would debug with `docker compose config` plus `exec env`.
_What the interviewer is probing for:_ Both precedence orders, and awareness that shell overrides `.env`.

**🎯 Senior:** _"A deploy shipped with an empty database password and the service started anyway. How do you prevent that class of failure, and what are the limits of environment variables for this?"_
**Model answer:** Use `${DB_PASSWORD:?DB_PASSWORD must be set}` so interpolation fails fast, and run `docker compose config` as a CI gate. Then reduce exposure: move credentials to Compose `secrets:` or the image's `*_FILE` convention so the value is a mounted file rather than an environment variable visible in `docker inspect` and process environments. Limits of env vars: they are readable by anyone with engine access, leak into logs and child processes, are fixed at container creation, and cannot be rotated without recreating the container. For stronger guarantees use an external secret manager and short-lived credentials.
_What the interviewer is probing for:_ Fail-fast configuration and honest treatment of secret exposure.

**🎯 Architect:** _"Design the configuration strategy for one Compose project deployed to dev, CI and a single-host production, with several teams contributing services."_
**Model answer:** One base `compose.yaml` containing no environment-specific literals; every varying value is an interpolation with a default for non-sensitive items and `:?` for required ones. Environment differences come from per-environment env files selected by `--env-file` or `COMPOSE_ENV_FILES`, plus override files and profiles for structural differences ([§38](Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)). Credentials come from `secrets:` backed by the host or a secret manager, never from files in Git. A committed `.env.example` is the contract, CI validates `docker compose config` for each environment, and image tags come from the pipeline. Per-service `env_file` scoping keeps teams from reading each other's variables, and a naming convention prevents collisions.
_What the interviewer is probing for:_ A layered, auditable approach rather than ad hoc `.env` editing.

## 12. Common Misconceptions

- "`.env` variables are automatically available inside containers." They are available to the Compose file only.
- "`env_file` and `.env` are the same thing." Different purpose, different precedence, different scope.
- "`environment:` in the YAML always loses to the file." It overrides `env_file:`.
- "Environment variables are a secure place for secrets." They are convenient, not confidential.
- "Editing `.env` updates running containers." Containers must be recreated.
- "The current directory always decides which `.env` is read." The project directory does, unless overridden.

## 13. 🔑 Key Takeaways

- Two mechanisms: interpolation (CLI, from shell > `--env-file` > `.env`) and container environment (`-e` > `environment:` > `env_file:` > image `ENV`).
- `.env` reaches a container only if `environment:` or `env_file:` names it.
- Use `${VAR:-default}` for optional and `${VAR:?msg}` for required values; `$$` escapes a dollar sign.
- `docker compose config` shows the resolved truth; run it before `up`.
- Env vars are visible and fixed at creation; prefer secrets for credentials.

## 14. Related Concepts & What's Next

Related: Compose file format ([§34](Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)), services and volumes ([§35](Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)), `ENV`/`ARG` ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), run-time flags ([§26](../Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)), secrets ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)), reproducible build args ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)). Next, [§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md) covers start-up ordering, so a service that needs a database waits until it is truly ready.

**Next Section:** [§37](Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md) — `Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md`
