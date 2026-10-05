# Section 19 (Part 3): WORKDIR, ENV, ARG, and LABEL

## 1. Definition

**Plain language:** These four Dockerfile instructions configure the *context* in which the rest of the build and the final container operate. `WORKDIR` sets the current directory. `ENV` sets environment variables that persist into the running container. `ARG` sets variables that exist only while building. `LABEL` attaches key/value metadata to the image.

**Precise definition:**

- **`WORKDIR /path`** sets the working directory for every following `RUN`, `CMD`, `ENTRYPOINT`, `COPY`, and `ADD`. If the directory does not exist it is created. Relative paths resolve against the previous `WORKDIR`. It is recorded in the image config (`Config.WorkingDir`, see [§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) and becomes the default cwd of containers.
- **`ENV KEY=value`** sets an environment variable in the image config (`Config.Env`). It is visible to later build steps and to every container started from the image, and can be overridden at run time with `-e`.
- **`ARG NAME[=default]`** declares a build-time variable supplied with `--build-arg`. It is *not* stored in `Config.Env`, so it is not present in running containers, but its value can still surface in image history (see Security).
- **`LABEL key=value`** adds OCI-style metadata to the image config (`Config.Labels`), readable through `docker inspect` and registry tooling.

> 💡 **Tip:** Think of `ENV` as "runtime and build", `ARG` as "build only", `WORKDIR` as "a persistent `cd`", and `LABEL` as "sticky notes for tooling and humans".

## 2. Why This Matters

- **`RUN cd /app && ...` does not persist.** Every `RUN` is a new shell in a new layer, so `WORKDIR` is the only correct way to change directory across instructions.
- **Configuration belongs in the environment.** Twelve-factor apps read config from env vars; `ENV` provides sane defaults while operators override them per deployment.
- **Parameterized builds** (base image version, tool versions, build target) are done with `ARG`, which keeps one Dockerfile useful for many variants and improves cache reuse.
- **Metadata makes images governable.** Labels such as source repository, revision, and licence let scanners, registries, and auditors trace an image back to its code (the OCI image spec defines standard `org.opencontainers.image.*` keys, [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)).
- **Mistakes here leak secrets.** Putting a token in `ENV` or `ARG` bakes it into image metadata for anyone who can pull the image.

## 3. Prerequisites and Dependencies

- Dockerfile basics: `FROM`, `RUN`, `COPY`, layers and cache behavior ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md) and [§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)).
- Understanding of the image config JSON that stores env, workdir, and labels ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)).
- Process environment basics: what an environment variable is and how child processes inherit it.
- The `CMD`/`ENTRYPOINT` exec vs shell form distinction ([§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), because variable expansion differs between them.
- OCI image spec annotations and label conventions ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)).

## 4. Architecture / Conceptual Diagram

```
  Build time only                          Build time AND run time
  ---------------                          -----------------------
  ARG  ──► available to RUN/ENV/etc.       ENV  ──► written to image config
       ──► NOT in Config.Env                    ──► visible in every container
       ──► value may appear in history          ──► overridable with -e

  FROM alpine:3.20
  ARG  APP_VERSION=1.0        # scope: from here to end of this build stage
  ENV  APP_HOME=/srv/app      # persisted in image config
  WORKDIR $APP_HOME           # creates /srv/app, sets cwd for later steps
  LABEL org.opencontainers.image.version=$APP_VERSION

          image config JSON (§16)
   ┌──────────────────────────────────────┐
   │ "Env":        ["APP_HOME=/srv/app"]  │◄── ENV
   │ "WorkingDir": "/srv/app"             │◄── WORKDIR
   │ "Labels":     {"...version":"1.0"}   │◄── LABEL
   │ (APP_VERSION absent)                 │◄── ARG leaves no Env entry
   └──────────────────────────────────────┘
```

Scope rules worth memorizing: an `ARG` declared *before* the first `FROM` is usable only in `FROM` lines; to use it in a stage it must be redeclared (`ARG NAME`) inside that stage. Each stage of a multi-stage build has its own `ARG` and `ENV` scope.

## 5. Hands-On

### 5.1 WORKDIR versus `cd`

```dockerfile
FROM alpine:3.20
RUN cd /tmp && pwd
RUN pwd
WORKDIR /srv/app
RUN pwd
WORKDIR logs
RUN pwd
```

```
$ docker build --progress=plain --no-cache . 2>&1 | grep -A1 "RUN pwd"
#5 [3/6] RUN pwd
#5 0.212 /
#7 [5/6] RUN pwd
#7 0.198 /srv/app
#9 [7/7] RUN pwd
#9 0.201 /srv/app/logs
```

The `cd /tmp` in the first `RUN` was forgotten immediately. The relative `WORKDIR logs` resolved to `/srv/app/logs`.

### 5.2 ENV defaults and run-time override

```dockerfile
FROM alpine:3.20
ENV APP_ENV=production \
    LOG_LEVEL=info
CMD ["sh", "-c", "echo env=$APP_ENV level=$LOG_LEVEL"]
```

```
$ docker build -t envdemo .
$ docker run --rm envdemo
env=production level=info
$ docker run --rm -e LOG_LEVEL=debug envdemo
env=production level=debug
$ docker inspect envdemo --format '{{json .Config.Env}}'
["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin","APP_ENV=production","LOG_LEVEL=info"]
```

### 5.3 ARG for parameterized builds

```dockerfile
ARG BASE_TAG=3.20
FROM alpine:${BASE_TAG}
ARG APP_VERSION=dev
RUN echo "building ${APP_VERSION}" > /version.txt
```

```
$ docker build -t argdemo --build-arg APP_VERSION=2.4.1 --build-arg BASE_TAG=3.19 .
$ docker run --rm argdemo cat /version.txt
building 2.4.1
$ docker run --rm argdemo env | grep APP_VERSION || echo "APP_VERSION not in runtime env"
APP_VERSION not in runtime env
```

Note the second `ARG` had to be declared after `FROM` because `BASE_TAG` (declared before `FROM`) is out of scope inside the stage.

### 5.4 Promoting an ARG into an ENV

```dockerfile
FROM alpine:3.20
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
```

`ENV` copies the build-time value into the image so the running app can read it (for example to report its version).

### 5.5 LABEL and querying labels

```dockerfile
FROM alpine:3.20
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.source="https://github.com/example/app" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.licenses="Apache-2.0" \
      maintainer="platform-team@example.com"
```

```
$ docker build -t labeldemo --build-arg GIT_SHA=$(git rev-parse --short HEAD) .
$ docker inspect labeldemo --format '{{json .Config.Labels}}'
{"maintainer":"platform-team@example.com","org.opencontainers.image.licenses":"Apache-2.0","org.opencontainers.image.revision":"fba412b","org.opencontainers.image.source":"https://github.com/example/app"}
$ docker images --filter "label=maintainer=platform-team@example.com"
REPOSITORY   TAG      IMAGE ID       CREATED          SIZE
labeldemo    latest   3f2a9c1d7b64   10 seconds ago   7.8MB
```

### 5.6 Seeing an ARG leak through history

```
$ docker history argdemo --no-trunc | head -4
IMAGE        CREATED         CREATED BY
sha256:...   2 minutes ago   RUN |1 APP_VERSION=2.4.1 /bin/sh -c echo "building ${APP_VERSION}" > /version.txt
```

The build-arg value is embedded in the history entry. Do not pass secrets this way.

## 6. Production Usage Notes

- **Always set `WORKDIR` with an absolute path** early in the Dockerfile; avoid chains of relative `WORKDIR` steps that are hard to audit.
- **Pin versions with `ARG` at the top** (`ARG NODE_VERSION=20`) so CI can bump a base by one flag; combine with digest pinning for reproducibility.
- **Stamp provenance** at build time: `--build-arg GIT_SHA=... --build-arg BUILD_DATE=...` mapped to OCI labels. Changing a value that appears early in the file invalidates the cache from that line onward, so place volatile `ARG`s late.
- **Group `ENV` instructions** in one instruction with backslashes; each is metadata only (no filesystem layer), but grouping keeps the file readable.
- **Prefer BuildKit's `--label` and `--annotation`** flags (or `docker/metadata-action` in CI) to generate labels consistently across many repos.
- **Predefined proxy args** (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`) are available without declaring `ARG`; useful behind corporate proxies.

## 7. Security Considerations

- **Never put secrets in `ENV`**: they appear in `docker inspect`, in `docker history`, and in the process environment of every container. Anyone with pull access reads them.
- **Never put secrets in `ARG`**: they are stored in the history metadata (5.6). Use BuildKit secret mounts (`RUN --mount=type=secret,id=npmrc ...`) or SSH mounts instead; they never land in a layer or the config.
- **Environment variables leak at run time** through `/proc/<pid>/environ`, crash dumps, and verbose logging; for runtime secrets prefer mounted files or a secrets manager.
- **Labels are public metadata.** Do not embed internal hostnames, ticket numbers, or credentials.
- **`WORKDIR` and permissions:** a `WORKDIR` created implicitly is owned by root. If the app runs as a non-root user ([§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), create and `chown` the directory explicitly.
- **Untrusted `--build-arg` values** interpolated into `RUN` lines can cause command injection in the build; treat build args as code inputs.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `$VAR` empty inside a `RUN` | `ARG` declared before `FROM` but used after it | Redeclare `ARG VAR` inside the stage |
| Variable missing at run time | Defined with `ARG`, not `ENV` | Add `ENV VAR=${VAR}` |
| `[Warning] One or more build-args [X] were not consumed` | `--build-arg` passed with no matching `ARG` | Declare the `ARG` or drop the flag |
| Env var not expanded in `CMD ["echo","$X"]` | Exec form has no shell | Use shell form or `["sh","-c","echo $X"]` ([§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) |
| Permission denied writing in WORKDIR | Directory created by root, app runs as non-root | `RUN mkdir` + `chown`, or `COPY --chown` |
| Cache rebuilds every time | Changing `ARG` (e.g. timestamp) placed early | Move volatile `ARG` below expensive steps |
| Old value persists in container | Overridden value ignored because `ENV` set again later | Check for repeated `ENV` of same key |

Debug commands: `docker inspect <img> --format '{{.Config.WorkingDir}}'`, `docker run --rm <img> env`, `docker history --no-trunc <img>`.

## 9. Best Practices

- Use `WORKDIR` instead of `RUN cd`, and use absolute paths.
- Use `ENV` for defaults only; let orchestrators inject real configuration.
- Declare `ARG` after `FROM` for stage-scoped values, and before `FROM` only for base image selection.
- Give `ARG`s safe defaults so the Dockerfile builds without flags.
- Apply the standard `org.opencontainers.image.*` label keys rather than inventing your own.
- Use `ENV` and `ARG` with the `KEY=value` syntax (the legacy `ENV KEY value` form is discouraged).
- Keep `ENV PATH` changes additive: `ENV PATH=/opt/tool/bin:$PATH`.
- Use BuildKit secret mounts for anything sensitive during builds.

## 10. Common Anti-Patterns / Mistakes

- `RUN cd /app` followed by another `RUN` that expects to be in `/app`.
- `ARG NPM_TOKEN` or `ENV AWS_SECRET_ACCESS_KEY=...` in a Dockerfile.
- Setting `ENV DEBIAN_FRONTEND=noninteractive` globally; it persists into the runtime image. Prefer `ARG DEBIAN_FRONTEND=noninteractive` or inline it on the `RUN`.
- Using `ARG` for a value the app needs at run time.
- A `BUILD_DATE=$(date)` arg early in the file, defeating the layer cache.
- Dozens of custom labels that nothing consumes.
- Relying on `WORKDIR` implicit creation as root, then running as a different user.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `ENV` and `ARG`, and why is `WORKDIR /app` better than `RUN cd /app`?"_
**Model answer:** `ARG` exists only at build time (set with `--build-arg`), while `ENV` is written into the image config and is present in every container. `RUN cd /app` changes directory only for that single RUN shell, so later instructions are back in the previous directory. `WORKDIR` persists across later instructions, is recorded in the image config, creates the directory if missing, and becomes the default working directory at run time. You can check labels and env with `docker inspect --format '{{json .Config.Env}}'`.
_What the interviewer is probing for:_ Build-time versus run-time scope and persistence of instructions.

**🎯 Intermediate:** _"You declare `ARG VERSION=1.2` before `FROM` and reference `$VERSION` in a later `RUN`, but it is empty. Also the app needs that value at run time. Explain and fix."_
**Model answer:** An ARG declared before the first `FROM` lives in a global scope usable only in `FROM` lines, such as `FROM node:${VERSION}`. Inside a stage you must redeclare it with `ARG VERSION` (no value needed) to bring it into scope. ARG values vanish at run time, so to expose it to the app copy it into an environment variable: `ARG VERSION` then `ENV APP_VERSION=$VERSION`. Override at build with `--build-arg VERSION=1.3`.
_What the interviewer is probing for:_ Stage and global ARG scoping rules and ARG-to-ENV bridging.

**🎯 Senior:** _"A developer passes `--build-arg NPM_TOKEN=...` and says it is safe because `docker inspect` shows no such env var. Is it safe, and how does it affect caching?"_
**Model answer:** It is not safe. Build args used by RUN are recorded in image history and cache metadata, so `docker history --no-trunc` or a saved image can reveal the value. Use `RUN --mount=type=secret,id=npm` with `docker build --secret id=npm,src=.npmrc` so the secret is mounted only for that step and never stored in a layer. On caching, a changed arg value invalidates the first instruction that consumes it and every later layer, so keep volatile args (like `GIT_SHA`) as late as possible in the Dockerfile.
_What the interviewer is probing for:_ Knowledge that ARG leaks via history and how it interacts with layer cache.

**🎯 Architect:** _"Design a configuration and provenance strategy for images promoted dev to staging to prod, across 200 repositories."_
**Model answer:** Build one immutable image and promote it by digest; never rebuild per environment. Use `ENV` only for non-sensitive defaults, and inject environment-specific config and secrets at deploy time via orchestrator config maps and a secret store. Generate OCI labels (`org.opencontainers.image.source`, `revision`, `version`, `created`) in CI from `GIT_SHA` and the repo URL using a metadata action, rather than hand-written LABELs. Enforce with a policy check that inspects `.Config.Labels` and rejects images lacking them, and add signed attestations. Labels then drive ownership routing, retention, and traceability from a running container back to a commit.
_What the interviewer is probing for:_ Immutable artifact promotion, secret separation, and label-based governance at scale.

## 12. Common Misconceptions

- "`ARG` values are secret." They are visible in history.
- "`ENV` set in an earlier stage carries into later stages." Each `FROM` starts fresh unless you inherit from that stage.
- "`WORKDIR` only works once." It can be used many times and relative paths stack.
- "Labels change container behavior." They are inert metadata.
- "`ENV` creates a filesystem layer." It only changes image metadata (a history entry with zero size).

## 13. 🔑 Key Takeaways

- `WORKDIR` persists; `cd` inside `RUN` does not.
- `ENV` is build plus runtime; `ARG` is build only.
- Neither `ENV` nor `ARG` is a safe place for secrets; use BuildKit secret mounts.
- `ARG` scope is per stage, and pre-`FROM` args must be redeclared.
- Labels carry provenance; use the OCI standard keys.
- Put volatile values late to preserve cache.

## 14. Related Concepts & What's Next

Related: image config JSON and history ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `RUN`/`COPY` semantics ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), `CMD` vs `ENTRYPOINT` and shell expansion ([§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)), OCI annotations ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), build context ([§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), and the build engine itself ([§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)). Inspecting labels and history is covered in [§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md). Run-time `-e` and `--env-file` flags are covered in the containers CLI topic later.

**Next Section:** [§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md) — `Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md`
