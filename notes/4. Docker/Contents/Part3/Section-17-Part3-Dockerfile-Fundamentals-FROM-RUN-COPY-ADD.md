# Section 17 (Part 3): Dockerfile Fundamentals: FROM, RUN, COPY, ADD

## 1. Definition

**Plain language:** A Dockerfile is a text recipe that tells Docker how to assemble an image: start from a base, run commands, copy files in. Each instruction becomes a step, and steps that change the filesystem become layers.

**Precise definition:** A **Dockerfile** is a declarative build script parsed by the builder (BuildKit by default). `FROM` sets the base image (or `scratch`) and starts a build stage; `RUN` executes a command in a temporary container and commits the filesystem delta as a layer; `COPY` copies files or directories from the build context (or another stage via `--from`) into the image; `ADD` does the same but additionally auto-extracts local tar archives and can fetch remote URLs or Git repositories. `RUN`, `COPY` and `ADD` create layers ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)); most other instructions only change image config.

> 💡 **Tip:** Prefer `COPY` over `ADD` unless you specifically need tar auto-extraction or a remote source with checksum. `COPY` is explicit and predictable.

## 2. Why This Matters

- The Dockerfile is the source of truth for how an image is built; it is code-reviewed and versioned like any other artifact.
- Instruction order determines **build cache** hits and therefore CI speed.
- Small choices (`&&` chaining, cleanup in the same `RUN`) decide final image size.
- `COPY` vs `ADD` and shell vs exec forms cause real bugs and security findings.
- Dockerfile fluency is baseline for the DCA exam and for any container interview.

## 3. Prerequisites and Dependencies

Understand image layers and manifests ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) and the OCI spec ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). Knowing how the daemon and the CLI hand a build to the builder ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)) helps. Later sections build on this one: [§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md) (CMD/ENTRYPOINT), [§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md) (WORKDIR/ENV/ARG/LABEL), [§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md) (.dockerignore and build context), [§24](Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md) (BuildKit).

## 4. Architecture / Conceptual Diagram

```text
  Dockerfile                                Resulting image layers
  ─────────────────────────────             ──────────────────────────
  FROM python:3.12-slim        ────────►    [base layers, from registry]
  RUN apt-get update && ...    ────────►    [layer: installed packages]
  COPY requirements.txt .      ────────►    [layer: requirements.txt]
  RUN pip install -r ...       ────────►    [layer: site-packages]
  COPY . .                     ────────►    [layer: app source]
  CMD ["python", "app.py"]     ────────►    (config only, no layer)

  Build context (dir sent to builder) ──► source for COPY/ADD
                    ▲
                    │ filtered by .dockerignore

  Cache rule: a step is reused only if its instruction and all
  inputs are unchanged AND every earlier step was a cache hit.
```

- **Cache invalidation cascades downward.** Change `requirements.txt` and every step after that `COPY` rebuilds.
- **`RUN` sees only what earlier layers produced**, plus mounts you explicitly request.
- **`COPY` sources are relative to the build context**, never the Dockerfile's directory unless they coincide.

## 5. Hands-On

### 5.1 A Minimal Dockerfile and Build

```dockerfile
FROM alpine:3.20
RUN apk add --no-cache curl
COPY hello.sh /usr/local/bin/hello.sh
RUN chmod +x /usr/local/bin/hello.sh
```

```bash
echo -e '#!/bin/sh\necho hello from $(hostname)' > hello.sh
docker build -t demo:1 .
```

```text
[+] Building 4.1s (8/8) FINISHED                          docker:default
 => [1/4] FROM docker.io/library/alpine:3.20@sha256:1e42...       1.2s
 => [2/4] RUN apk add --no-cache curl                              2.3s
 => [3/4] COPY hello.sh /usr/local/bin/hello.sh                    0.0s
 => [4/4] RUN chmod +x /usr/local/bin/hello.sh                     0.2s
 => exporting to image                                             0.1s
 => => naming to docker.io/library/demo:1                          0.0s
```

### 5.2 `FROM`: Base Images, Stages, `scratch`, and Args

```dockerfile
ARG PY_VERSION=3.12
FROM python:${PY_VERSION}-slim AS base
FROM scratch AS empty
FROM --platform=linux/amd64 alpine:3.20 AS pinned
```

- `AS name` names a stage for `COPY --from=name`.
- `ARG` is the only instruction allowed before the first `FROM`.
- `--platform` forces a specific platform of a multi-arch base.

### 5.3 `RUN`: Shell Form vs Exec Form and Layer Hygiene

```dockerfile
# shell form: runs via /bin/sh -c, variable expansion works
RUN echo "building on $(uname -m)"

# exec form: no shell, no expansion, must call the binary directly
RUN ["/bin/echo", "no shell here"]

# good: one layer, cleanup in the same step
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
```

Compare layer sizes:

```bash
docker history --format '{{.Size}}\t{{.CreatedBy}}' demo:2
```

```text
41.2MB	RUN /bin/sh -c apt-get update && apt-get install ...
```

Splitting install and cleanup into two `RUN`s would keep the ~30MB of apt lists in the first layer.

### 5.4 `RUN` Extras with BuildKit: Cache and Secret Mounts

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install flask
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    echo "secret available only during this step"
```

```bash
docker build --secret id=npmrc,src=$HOME/.npmrc -t demo:3 .
```

Secret mounts never land in a layer or in `docker history`.

### 5.5 `COPY`: Files, Ownership, and Multi-Stage

```dockerfile
FROM golang:1.23 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app .

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/app /app
COPY --chown=65532:65532 config.yaml /etc/app/config.yaml
ENTRYPOINT ["/app"]
```

- Copy dependency manifests first, then source, to keep the dependency layer cached.
- `--chown` and `--chmod` set ownership/permissions without an extra `RUN chown` layer.
- Trailing `/` on the destination matters: `COPY a b` with multiple sources requires `b/`.

### 5.6 `ADD`: When It Differs from `COPY`

```dockerfile
# auto-extracts a local tar into /opt/app
ADD app-release.tar.gz /opt/app/

# remote file, verified by checksum (BuildKit)
ADD --checksum=sha256:9f2e...c1 https://example.com/tool.tgz /tmp/tool.tgz

# Git repository as build source
ADD https://github.com/example/repo.git#v1.2.0 /src
```

Remote `ADD` files are not extracted automatically. For downloads, `RUN curl ... && rm` in one layer or a checksummed `ADD` is safer than an unverified URL.

### 5.7 Demonstrating Cache Behavior

```bash
docker build -t demo:4 .        # first build
touch app.py
docker build -t demo:4 .        # second build
```

```text
 => CACHED [2/5] RUN pip install -r requirements.txt   0.0s
 => [4/5] COPY . .                                       0.1s
```

## 6. Production Usage Notes

- Use multi-stage builds so compilers and test tools never ship.
- Pin base images by version, ideally by digest, and update them on a schedule.
- Add `# syntax=docker/dockerfile:1` to get current frontend features predictably.
- Combine related commands with `&&` and clean up in the same layer; use `\` continuations sorted alphabetically for package lists.
- Use `--no-install-recommends` (apt) or `--no-cache` (apk) to keep layers lean.
- Lint with `hadolint` in CI.

## 7. Security Considerations

- **Never `COPY` secrets** (`.env`, keys, `.npmrc`) into an image; use BuildKit secret mounts.
- **`ADD <url>` without checksum** trusts whatever the remote serves; prefer `--checksum` or verified downloads.
- **`curl | sh` in `RUN`** executes unverified code at build time.
- **Unpinned `FROM latest`** silently pulls changes, including compromised ones.
- Use a non-root user (see `USER` in a later section) and minimal bases.
- Filter the build context so `.git` and credentials are never sent ([§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `COPY failed: file not found in build context` | Path outside context or excluded by `.dockerignore` | Check the context root and ignore rules ([§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)) |
| `apt-get: E: Unable to locate package` | `update` in a separate, cached layer | Chain `update && install` in one `RUN` |
| Build always reruns `pip install` | `COPY . .` before dependency manifest | Copy manifests first |
| `/bin/sh: 1: [: unexpected operator` | Bash syntax under `sh` | Use `SHELL ["/bin/bash","-c"]` or POSIX syntax |
| Extracted tar unexpectedly | Used `ADD` on a local `.tar.gz` | Use `COPY` if extraction is not wanted |
| Files owned by root, app cannot write | Missing `--chown` | `COPY --chown=user:group` |

## 9. Best Practices

- Order instructions from least to most volatile.
- Use `COPY`, not `ADD`, by default.
- One clear purpose per `RUN`; clean up in the same layer.
- Use exec form for anything that must receive signals or run without a shell.
- Use multi-stage builds and `COPY --from`.
- Pin versions of OS packages and language dependencies where feasible.
- Keep the Dockerfile at a sensible context root and use `.dockerignore`.

## 10. Common Anti-Patterns / Mistakes

- `RUN apt-get update` alone on its own line (stale cache problem).
- Installing build tools and leaving them in the final image.
- `COPY . .` as the first step after `FROM`.
- Using `ADD` for plain file copies.
- Deleting files in a later layer to "reduce size".
- `RUN cd dir && ...` habits instead of `WORKDIR` (see [§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).
- Embedding tokens in `RUN` commands or `ARG` values.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `RUN`, `CMD`, and `ENTRYPOINT`, and when does each execute?"_
**Model answer:** `RUN` executes at build time and commits a new layer, for example installing packages. `CMD` and `ENTRYPOINT` define what runs at container start: ENTRYPOINT is the fixed executable and CMD supplies default arguments that `docker run image args` can override. Use exec form (`["nginx", "-g", "daemon off;"]`) so the process is PID 1 and receives signals. Only the last `CMD` and the last `ENTRYPOINT` in a Dockerfile take effect.
_What the interviewer is probing for:_ Build time versus run time and exec form.

**🎯 Intermediate:** _"What are the differences between `COPY` and `ADD`, and which should you prefer?"_
**Model answer:** `COPY` copies local files or directories from the build context into the image and nothing else. `ADD` also auto-extracts local tar archives and can fetch remote URLs, which makes behavior less predictable and remote content unverified. Prefer `COPY`, and use `ADD` only for deliberate local tar extraction (or `ADD --checksum` for remote files on BuildKit). For downloads, use `RUN curl` with checksum verification.
_What the interviewer is probing for:_ Preference for explicit, predictable instructions.

**🎯 Senior:** _"A Dockerfile rebuilds every dependency on each source change and produces a large image. How do you fix layer caching and size?"_
**Model answer:** Cache invalidates at the first changed instruction and everything after it, so copy dependency manifests first (`COPY package.json package-lock.json ./`), run the install, and only then `COPY . .`. Combine `apt-get update && apt-get install --no-install-recommends ... && rm -rf /var/lib/apt/lists/*` in one `RUN` so cleanup is in the same layer. Add a `.dockerignore` to keep `.git` and `node_modules` out of the context, and use BuildKit cache mounts (`RUN --mount=type=cache,target=/root/.cache`). Verify with `docker history` and `docker build --progress=plain`.
_What the interviewer is probing for:_ Layer ordering, same-layer cleanup, and build-context hygiene.

**🎯 Architect:** _"Define standards for Dockerfiles across many teams so builds are reproducible, small, and secure."_
**Model answer:** Require pinned base images by digest, multi-stage builds so compilers and secrets stay out of the final image, a non-root `USER`, exec-form entrypoints, and `HEALTHCHECK` where an orchestrator does not supply probes. Lint with hadolint in CI, scan images, generate SBOMs and provenance attestations with BuildKit, and publish blessed base images that a central team patches and rebuilds regularly. Enforce with policy checks rather than documentation alone. The trade-off is reduced team autonomy, offset by paved-road templates that make the compliant path the easiest.
_What the interviewer is probing for:_ Governance and supply-chain thinking at organizational scale.

## 12. Common Misconceptions

- "Each Dockerfile line is a layer." Only filesystem-changing steps produce layers.
- "`ADD` is just a more powerful `COPY`, so use it always." Its magic behaviors are a source of surprises.
- "`RUN rm` shrinks the image." Not across layers.
- "`FROM` must be the first line." Only `ARG` (and comments/parser directives) may precede it.

## 13. 🔑 Key Takeaways

- `FROM` picks the base, `RUN` executes and commits, `COPY` moves files in, `ADD` adds extraction and remote fetch.
- Layer order drives cache efficiency; put volatile content last.
- Clean up in the same layer that made the mess.
- Prefer `COPY`; use `ADD` only for tar auto-extract or checksummed remote sources.
- Never bake secrets into any instruction; use secret mounts.

## 14. Related Concepts & What's Next

Related: image layers ([§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), OCI specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), union filesystems ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). Next, [§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md) explains how `CMD` and `ENTRYPOINT` define what runs when the container starts; [§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md) and [§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md) cover the remaining configuration instructions; [§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md) covers the build context.

**Next Section:** [§18](Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md) — `Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md`
