# Section 24 (Part 3): Building Images: docker build and BuildKit Basics

## 1. Definition

**Plain language:** `docker build` reads a Dockerfile and a folder of files (the build context) and produces an image. BuildKit is the modern engine behind that command: it builds faster, runs independent steps in parallel, caches smartly, and supports secrets and cache mounts.

**Precise definition:** `docker build` is a client command that sends a build context and a Dockerfile to a builder, which executes each instruction to produce layers ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)) and finally an image config and manifest. **BuildKit** is a builder that converts the Dockerfile into a low-level build graph (LLB), a directed acyclic graph of operations, solves it with parallel execution and content-addressable caching, and exports the result. Since Docker Engine 23.0, BuildKit is the default builder on Linux, and `docker build` is an alias for `docker buildx build`. Docker Desktop has used it by default for longer. The legacy builder is deprecated.

> 💡 **Tip:** Think of the build as a graph of cacheable steps, not a script. Order instructions from least to most frequently changing.

## 2. Why This Matters

- **Build time is developer and CI time.** Correct layer ordering and cache use often turns 5-minute builds into 20-second ones.
- **Image size and security** are decided at build time: multi-stage builds, minimal bases, and no leaked secrets.
- **Reproducibility and provenance:** BuildKit can emit SBOMs and provenance attestations.
- **Multi-platform builds** (amd64 and arm64) require buildx and BuildKit.
- **Interviews and DCA:** cache invalidation rules and `--no-cache`, `--target`, `--build-arg` come up constantly.

## 3. Prerequisites and Dependencies

Requires Dockerfile instructions ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)-[§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), the build context and `.dockerignore` ([§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), base images ([§22](Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)), tagging ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), and layers ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md), [§16](Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)). The engine components involved are described in [§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md) and the client/API split in [§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md); the `docker build` client streams the context to the daemon (or to a buildx builder) over the API.

## 4. Architecture / Conceptual Diagram

```text
  docker build -t myorg/api:1.4.2 .
        │
        ▼
  ┌───────────────┐   context tarball / Dockerfile    ┌─────────────────────────┐
  │ Docker CLI    │──────────────────────────────────►│ BuildKit (buildkitd)    │
  │ (buildx)      │◄──────── progress stream ─────────│                         │
  └───────────────┘                                   │  Dockerfile ► LLB graph │
                                                      │        │                │
                                                      │   ┌────┴─────┐          │
                                                      │   ▼          ▼          │
                                                      │ stage: build  stage: base
                                                      │   │  (parallel where    │
                                                      │   │   independent)      │
                                                      │   ▼                     │
                                                      │ cache lookup per step ──┼──► local cache /
                                                      │  hit: reuse layer       │    registry cache
                                                      │  miss: run with runc    │
                                                      │        │                │
                                                      └────────┼────────────────┘
                                                               ▼
                                            exporter: docker image store / registry / OCI tar
```

- The context is sent incrementally: BuildKit requests only the files a step needs (`COPY`), unlike the legacy builder, which sent everything up front.
- Each instruction's cache key includes the instruction text, parent layer, and (for `COPY`/`ADD`) the checksum of the files. A miss invalidates all later steps.
- Unused stages are skipped entirely, and independent stages run concurrently.

## 5. Hands-On

### 5.1 A basic build

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "app.py"]
```

```bash
$ docker build -t myorg/api:1.4.2 .
[+] Building 18.4s (10/10) FINISHED                          docker:default
 => [internal] load build definition from Dockerfile                    0.0s
 => [internal] load metadata for docker.io/library/python:3.12-slim     0.9s
 => [internal] load .dockerignore                                       0.0s
 => [1/5] FROM docker.io/library/python:3.12-slim@sha256:...            4.1s
 => [2/5] WORKDIR /app                                                  0.1s
 => [3/5] COPY requirements.txt .                                       0.0s
 => [4/5] RUN pip install --no-cache-dir -r requirements.txt           11.8s
 => [5/5] COPY . .                                                      0.1s
 => exporting to image                                                  1.2s
 => => naming to docker.io/myorg/api:1.4.2                              0.0s
```

Dependencies are installed before the source is copied, so editing code invalidates only the last `COPY`.

### 5.2 Cache in action

```bash
$ docker build -t myorg/api:1.4.2 .
 => CACHED [2/5] WORKDIR /app                                           0.0s
 => CACHED [3/5] COPY requirements.txt .                                0.0s
 => CACHED [4/5] RUN pip install --no-cache-dir -r requirements.txt     0.0s
 => [5/5] COPY . .                                                      0.1s
```

Use `--no-cache` to force a full rebuild and `--pull` to refresh the base image.

### 5.3 Build arguments, Dockerfile path, and targets

```bash
$ docker build -f docker/Dockerfile.prod --build-arg APP_VERSION=1.4.2 --target runtime -t myorg/api:1.4.2 .
```

- `-f` selects the Dockerfile; the trailing `.` remains the context.
- `--build-arg` feeds an `ARG` ([§19](Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).
- `--target` stops at a named stage (`FROM ... AS runtime`).

### 5.4 Multi-stage build

```dockerfile
FROM golang:1.22 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/api ./cmd/api

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/api /api
USER 65532:65532
ENTRYPOINT ["/api"]
```

The final image contains only the binary, not the Go toolchain.

### 5.5 Cache mounts and secrets (BuildKit features)

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc \
    npm ci
```

```bash
$ docker build --secret id=npmrc,src=$HOME/.npmrc -t myorg/web:dev .
```

Cache mounts persist package caches between builds without adding them to a layer. Secret mounts expose a file only for that `RUN` and leave nothing in the image or history.

### 5.6 Progress output and buildx

```bash
$ docker build --progress=plain -t myorg/api:dev .      # full logs instead of the TTY view
$ docker buildx ls
NAME/NODE       DRIVER/ENDPOINT   STATUS    BUILDKIT   PLATFORMS
default*        docker
  default       default           running   v0.15.1    linux/amd64, linux/arm64
$ docker buildx build --platform linux/amd64,linux/arm64 -t myorg/api:1.4.2 --push .
```

Multi-platform output cannot be loaded into the classic image store in one image, so it is typically pushed with `--push` (or exported as OCI). Exact BuildKit versions and platforms vary by installation.

### 5.7 Registry-backed cache for CI

```bash
$ docker buildx build \
    --cache-from type=registry,ref=myorg/api:buildcache \
    --cache-to   type=registry,ref=myorg/api:buildcache,mode=max \
    -t myorg/api:1.4.2 --push .
```

Ephemeral CI runners start with no local cache, so exporting it to a registry (or the `gha` cache type on GitHub Actions) restores incremental builds.

## 6. Production Usage Notes

- Build in CI with a fresh, pinned builder; push a SHA tag and version tag ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- Export and reuse cache (`--cache-to/--cache-from`) so CI builds are incremental.
- Use multi-stage builds to keep compilers out of runtime images; use `--target` to build test stages in CI.
- Add `# syntax=docker/dockerfile:1` to pick up current frontend features regardless of engine version.
- `--provenance` and `--sbom` attach attestations; recent buildx versions add provenance by default in some modes, which changes the manifest structure (an index rather than a single manifest), so check registries and scanners compatibility.
- Keep the context small with `.dockerignore` ([§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)); a large context slows every build.
- Rootless and remote builders (`docker buildx create --driver docker-container`) isolate builds from the host daemon.

## 7. Security Considerations

- **Never `COPY` secrets or pass them via `ARG`/`ENV`:** they persist in layers and `docker history` ([§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)). Use `--mount=type=secret` or SSH mounts (`--ssh`).
- `.git`, `.env`, and credentials in the context can leak through `COPY . .`; exclude them.
- Pin base images by digest ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)) and rebuild regularly to pick up patches (`--pull`).
- Run the final stage as a non-root user ([§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)).
- Builds execute arbitrary `RUN` commands: treat CI builders as sensitive, avoid privileged builders shared across tenants.
- Verify provenance and sign the pushed image.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `COPY failed: file not found in build context` | Path outside context or excluded by `.dockerignore` | Fix path; check `.dockerignore`; context is the final argument |
| Cache never hits | `COPY . .` before dependency install; changing timestamps or `ARG` early | Reorder; copy manifests first; move volatile `ARG`s later |
| Stale package versions in image | Cached `apt-get update` layer | Combine `apt-get update && apt-get install` in one `RUN`; use `--no-cache` occasionally |
| `failed to solve: ... not found` on `FROM` | Wrong image name/tag or missing auth | `docker login`; check the reference |
| Build very slow at "sending context" | Huge context (`node_modules`, `.git`) | Add `.dockerignore` |
| `multiple platforms feature is currently not supported for docker driver` | Default driver cannot build multi-platform | `docker buildx create --use --driver docker-container` |
| Old-style output, no `--mount` support | Legacy builder in use | Ensure BuildKit (`DOCKER_BUILDKIT=1` on older engines) |

## 9. Best Practices

- Order instructions from least to most volatile; copy dependency manifests before source.
- Use multi-stage builds and a minimal final base.
- Use BuildKit cache mounts for package managers and secret mounts for credentials.
- Always set a `.dockerignore`.
- Chain related shell commands in one `RUN` and clean up in the same layer.
- Build once, tag uniquely, push, and promote the same image.
- Lint Dockerfiles (hadolint) and scan built images in CI.
- Use `--progress=plain` to debug failing builds.

## 10. Common Anti-Patterns / Mistakes

- `COPY . .` as the first instruction after `FROM`, defeating caching.
- Baking secrets in with `ARG`, `ENV`, or `COPY`, then "deleting" them in a later layer (they remain in earlier layers).
- Building on the production host instead of in a controlled CI builder.
- Relying on `latest` bases with no `--pull` or pinning strategy.
- Installing build tools in the final image instead of using stages.
- Running `apt-get update` in a separate `RUN` from `install`.
- Ignoring the build context size.

## 11. Interview Questions

**🎯 Beginner:** _"What does `docker build -t shop:1.0 .` do, and what is the trailing dot?"_
**Model answer:** It reads `./Dockerfile`, sends the current directory as the build context, executes each instruction producing layers, and tags the result `shop:1.0`. The dot is the context path, not the Dockerfile location; use `-f path/Dockerfile` to pick a different file. With BuildKit (default on modern Engine) progress is shown as parallel steps, and `--progress=plain` shows full output.
_What the interviewer is probing for:_ Basic build mechanics.

**🎯 Intermediate:** _"How does the layer cache decide to reuse a step, and how do you pass a secret to a build safely?"_
**Model answer:** A step is reused when the instruction text, its parent layer, and (for COPY/ADD) the file checksums are unchanged; a miss invalidates every following step, so order rarely-changing steps first, such as copying the manifest and installing dependencies before `COPY . .`. For secrets use `docker build --secret id=token,src=token.txt` with `RUN --mount=type=secret,id=token cat /run/secrets/token`; the secret is mounted only during that step and not stored in layers. A multi-stage build with `COPY --from` keeps toolchains out of the final image.
_What the interviewer is probing for:_ Cache invalidation rules and safe secret handling.

**🎯 Senior:** _"CI builds on ephemeral runners take 15 minutes because nothing is cached. What do you change, and what does BuildKit do differently from the legacy builder?"_
**Model answer:** Export and import cache with `--cache-to type=registry,ref=...,mode=max` and `--cache-from` (or `type=gha`), order the Dockerfile for cache hits, add `RUN --mount=type=cache` for package managers, and shrink the context. BuildKit compiles the Dockerfile into an LLB graph, so independent stages run in parallel and unused stages are skipped, transfers the context incrementally, and supports secret and SSH mounts and attestations, none of which the legacy builder offers. Run with `docker buildx build`.
_What the interviewer is probing for:_ Concrete CI acceleration and BuildKit internals.

**🎯 Architect:** _"Design a build platform for many teams covering isolation, caching, provenance, and multi-arch, and discuss `mode=max` versus `mode=min`."_
**Model answer:** Use remote buildx builders (Kubernetes driver or a managed service) with rootless or per-job isolated workers, shared registry cache backends, and QEMU or native nodes for `--platform linux/amd64,linux/arm64`. Emit SBOM and provenance attestations (`--attest`), sign with cosign, run policy checks, and feed from a curated base-image pipeline. `mode=min` exports only final-image layers, which is small and quick but misses intermediate stage hits; `mode=max` exports all layers for better hit rates at higher storage and push time. Pick max for multi-stage heavy builds and add cache expiry.
_What the interviewer is probing for:_ Platform-level trade-offs across isolation, speed, and supply-chain integrity.

## 12. Common Misconceptions

- "Docker builds run on the client." The build runs in the builder (daemon or BuildKit), only the context is sent from the client.
- "Deleting a file in a later `RUN` removes it from the image." The earlier layer still holds it.
- "BuildKit is a separate tool you must install." It is bundled with modern Docker Engine and Docker Desktop.
- "`--no-cache` also refreshes the base image." It does not; use `--pull`.
- "More layers means a slower image." Layers matter less than size and cache behavior; the historical layer limit is not the practical concern.

## 13. 🔑 Key Takeaways

- `docker build` sends a context and Dockerfile to a builder; BuildKit is the default modern builder.
- Cache hits depend on instruction order: stable steps first, volatile steps last.
- Multi-stage builds separate build tooling from the runtime image.
- Use secret and cache mounts instead of baking credentials or bloating layers.
- Export cache to a registry for CI, and use buildx for multi-platform images.
- Tag and push each build uniquely ([§23](Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), then inspect the result ([§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)).

## 14. Related Concepts & What's Next

Related: Dockerfile instructions ([§17](Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)-[§20](Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), `.dockerignore` and context ([§21](Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), layers and overlay2 ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)), the engine ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), the API ([§9](../Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)). Next, [§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md) shows how to inspect the built image with `docker inspect`, `docker history`, and `dive` to verify layer contents and size.

**Next Section:** [§25](Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md) — `Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md`
