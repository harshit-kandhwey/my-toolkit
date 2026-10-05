# Section 75 (Part 10): BuildKit Deep Dive: Features and Syntax

## 1. Definition

**Plain language:** BuildKit is the modern engine that actually executes `docker build`. It reads your Dockerfile, turns it into a graph of independent steps, runs steps in parallel where it can, skips what it does not need, and adds advanced Dockerfile features such as cache mounts, secret mounts, heredocs and multiple output formats.

**Precise definition:** BuildKit (`moby/buildkit`) is a standalone build daemon, `buildkitd`, with a gRPC API. A **frontend** (the Dockerfile frontend `dockerfile.v0`, shipped as the image `docker/dockerfile`) parses a build definition into **LLB** (low-level build), a content-addressable, DAG-shaped intermediate representation. The solver executes the LLB graph using a **worker** (runc/containerd based, executing each `RUN` in an isolated container), caches vertices by content-based keys ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), and hands results to an **exporter** (image, OCI, tar, local directory, registry). It has been the default builder in Docker Engine since 23.0 (and in Docker Desktop earlier); `docker build` talks to it, and `docker buildx build` exposes the full feature set including builder instances, multi-platform output and remote cache backends. `DOCKER_BUILDKIT=0` selects the deprecated legacy builder on Linux Engine.

> 💡 **Tip:** Put `# syntax=docker/dockerfile:1` on the first line. It tells BuildKit to fetch the latest stable 1.x Dockerfile frontend, so you get new syntax without upgrading the Docker daemon.

## 2. Why This Matters

- Parallel stage execution, skipped unused stages and content-based caching cut build time compared with the legacy sequential builder.
- Features that were impossible before (secret mounts, SSH forwarding, cache mounts, heredocs) exist only with BuildKit.
- It underpins `docker buildx`, multi-platform images ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)), SBOM and provenance attestations, and most CI build tooling.
- Interviewers ask about the frontend/LLB/solver split to test whether you understand why `# syntax=` works and why builds behave differently from the legacy builder.
- Knowing the output formats lets you build without a daemon-visible image (for example exporting a binary to disk).

## 3. Prerequisites and Dependencies

Builds and the legacy-vs-BuildKit distinction ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), Dockerfile instructions ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), layers and manifests ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), and engine components ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)). Caching behavior from [§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md) and multi-stage builds from [§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md) are used throughout. Secrets and SSH are expanded in [§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md); multi-platform pipelines in [§79](Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md).

## 4. Architecture / Conceptual Diagram

```text
  docker build / docker buildx build                    (client)
        │  gRPC session: build context, secrets, ssh agent, auth
        ▼
  ┌─────────────────────────── buildkitd ──────────────────────────────┐
  │                                                                    │
  │  Frontend            LLB graph (DAG)               Solver          │
  │  ┌──────────────┐    ┌──────────────────────┐     ┌────────────┐   │
  │  │ dockerfile.v0│──► │ source ─► exec ─► exec│ ──►│ cache keys │   │
  │  │ (# syntax=)  │    │ source ─► exec ──┐    │    │ parallelism│   │
  │  │ gateway/other│    │            merge ─┘   │    └─────┬──────┘   │
  │  └──────────────┘    └──────────────────────┘          │           │
  │                                                         ▼           │
  │                        Worker (runc / containerd) executes each     │
  │                        RUN in an isolated rootfs + mounts          │
  │                                                         │           │
  │  Cache store ◄── --cache-to / --cache-from ──► remote   │           │
  └─────────────────────────────────────────────────────────┼───────────┘
                                                            ▼
        Exporters:  image (docker store) │ registry push │ oci │ tar │ local dir

  Independent branches run in parallel:

     FROM golang AS build-api ──┐
     FROM node   AS build-web ──┼──► FROM alpine (COPY --from=build-api, --from=build-web)
     FROM scratch AS assets  ───┘          (unreferenced stages are never built)
```

- **Frontend:** translates Dockerfile text into LLB; pluggable via `# syntax=`.
- **Solver:** walks the DAG from the requested target backwards, building only what is needed, concurrently.
- **Worker:** executes `RUN` steps; mounts (cache, secret, ssh, bind, tmpfs) are attached here.
- **Exporter:** decides the output: image, registry, OCI layout, tarball, or plain files via `type=local`.
- **Drivers (buildx):** `docker` (built into dockerd, limited), `docker-container`, `kubernetes`, `remote`.

## 5. Hands-On

### 5.1 Enabling and Confirming BuildKit

```bash
docker version --format '{{.Server.Version}}'
docker buildx version
docker buildx ls
docker build --progress=plain -t demo . 2>&1 | head
```

```text
NAME/NODE       DRIVER/ENDPOINT   STATUS    BUILDKIT   PLATFORMS
default*        docker
 \_ default      \_ default       running   v0.17.x    linux/amd64, linux/arm64 ...
```

On Engine 23+ BuildKit is on by default. `--progress` modes are `auto`, `plain` (full logs, best for CI) and `tty`. To create a dedicated builder with more features (cache export, multi-platform):

```bash
docker buildx create --name bk --driver docker-container --use
docker buildx inspect --bootstrap
```

### 5.2 Syntax Directive and Parser Directives

```dockerfile
# syntax=docker/dockerfile:1
# escape=\
FROM alpine:3.20
```

Parser directives must come first, before comments, blank lines or instructions. Use `docker/dockerfile:1` (rolling 1.x) or pin a version such as `docker/dockerfile:1.10` for repeatability ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)). The frontend image is pulled from a registry, so air-gapped builders must mirror it or omit the directive.

### 5.3 Mount Types for RUN

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim

# cache: persistent package cache
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install flask

# bind: read-only view of context (or another stage) files, no layer created
RUN --mount=type=bind,source=requirements.txt,target=/tmp/requirements.txt \
    pip install -r /tmp/requirements.txt

# bind from another stage
RUN --mount=type=bind,from=build,source=/out,target=/in ls /in

# tmpfs: scratch memory-backed dir
RUN --mount=type=tmpfs,target=/tmp/scratch,size=64m ./do-work.sh

# secret: file or env, never stored in a layer (details in 76)
RUN --mount=type=secret,id=token,target=/run/secrets/token \
    cat /run/secrets/token > /dev/null

# ssh: forward the host agent (details in 76)
RUN --mount=type=ssh git ls-remote git@github.com:org/private.git
```

| Mount | Persists in image? | Typical use |
|---|---|---|
| `cache` | No (survives across builds) | pip/npm/apt/go caches; `sharing=shared\|private\|locked` |
| `bind` | No | Use manifests or artifacts without `COPY` |
| `tmpfs` | No | Large scratch space |
| `secret` | No | Tokens, certs |
| `ssh` | No | Private git over SSH |

Useful options: `cache` takes `id`, `sharing`, `uid`, `gid`, `mode`; `bind` is read-only unless `rw` is set (writes are discarded); `secret` takes `id`, `target`, `env`, `required`.

### 5.4 Heredocs: Multi-Line RUN and Inline Files

```dockerfile
# syntax=docker/dockerfile:1
FROM debian:bookworm-slim

RUN <<EOF
set -eux
apt-get update
apt-get install -y --no-install-recommends curl ca-certificates
rm -rf /var/lib/apt/lists/*
EOF

COPY <<'EOF' /etc/app/config.ini
[server]
port = 8080
EOF

RUN <<PYEOF
#!/usr/bin/env python3
print("heredoc with a shebang runs with that interpreter")
PYEOF
```

Heredocs avoid `&& \` chains and let you create files without a separate context file. Quote the delimiter (`<<'EOF'`) to prevent variable expansion in the body. A shebang selects the interpreter for that `RUN`.

### 5.5 Frequently Useful Dockerfile Features

```dockerfile
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM golang:1.23 AS build
ARG TARGETOS TARGETARCH
WORKDIR /src
COPY --link go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY --link . .
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o /out/app ./cmd/app

FROM gcr.io/distroless/static-debian12:nonroot
COPY --link --from=build /out/app /app
ENTRYPOINT ["/app"]
```

- `COPY --link` creates the layer independently of earlier layers, so a changed base or earlier layer does not force re-creating this one, and layers can be rebased cheaply on push.
- `COPY --chmod=755` and `--chown=user:group` set mode/ownership without an extra `RUN`.
- `--platform=$BUILDPLATFORM` plus `TARGETOS`/`TARGETARCH` builds natively on the build host and cross-compiles ([§79](Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)).
- `ADD --checksum=sha256:...` verifies remote downloads; `ADD <git-url>#<ref>` fetches a repository; `COPY --exclude=` skips patterns.
- `RUN --network=none` blocks network for a step (hermetic compile); `RUN --network=host` needs the `network.host` entitlement.
- `ONBUILD`, `HEALTHCHECK` and `SHELL` behave as in the legacy builder.

### 5.6 Exporters and Outputs

```bash
# default: load into the local docker image store
docker buildx build -t app:dev --load .

# push directly
docker buildx build -t registry.example.com/app:1.0 --push .

# export files only (no image): extract the compiled binary
docker buildx build --target artifact --output type=local,dest=./out .

# OCI layout tarball
docker buildx build --output type=oci,dest=app.oci.tar .

# tar of the final filesystem
docker buildx build --output type=tar,dest=rootfs.tar .
```

An artifact stage for the `type=local` example:

```dockerfile
FROM scratch AS artifact
COPY --from=build /out/app /app
```

With the `docker-container` driver, results are not in the local Docker image store unless you pass `--load` (single platform) or `--push`.

### 5.7 Build Checks, Targets, and Bake

```bash
docker buildx build --check .                 # lint the Dockerfile (Build Checks), no build
docker buildx build --call check .            # equivalent explicit form
docker buildx build --call outline .          # list stages, args, secrets used
docker buildx build --target test .
docker buildx build --build-context mylib=../mylib .   # extra named contexts for COPY --from=mylib
```

`docker buildx bake` builds multiple targets from `docker-bake.hcl` (or a Compose file) in parallel with one `docker buildx bake` command.

### 5.8 Attestations: SBOM and Provenance

```bash
docker buildx build --sbom=true --provenance=mode=max -t registry.example.com/app:1.0 --push .
docker buildx imagetools inspect registry.example.com/app:1.0 --format '{{json .SBOM}}'
```

BuildKit can attach an SBOM (via the Syft scanner image) and SLSA provenance as attestation manifests next to the image ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Note that adding attestations turns a single-platform push into an index (manifest list) with extra entries, which some older registries and tools handle poorly.

### 5.9 Builder Configuration

GC policy, parallelism and registry mirrors live in `buildkitd.toml`, passed with `docker buildx create --name bk --driver docker-container --config ./buildkitd.toml --use`. Inspect and trim cache with `docker buildx du` and `docker buildx prune --keep-storage 10GB`; use `--progress=plain` when debugging.

## 6. Production Usage Notes

- **Use a `docker-container` builder in CI** for cache export, multi-platform and attestations; the default `docker` driver cannot export most cache types.
- **Pin both the frontend and the builder image** (`docker/dockerfile:1.10`, `--driver-opt image=moby/buildkit:v0.17.0`) when you need stable behavior across a fleet.
- **Remote builders:** `kubernetes`, `remote`, or Docker Build Cloud offload CPU and keep a warm shared cache. Authenticate and isolate them as you would any build infrastructure.
- **Plain progress in CI**, `tty` locally; failed steps then show complete logs.
- **Compose** uses BuildKit through `docker compose build` and can delegate to bake (`COMPOSE_BAKE`).

## 7. Security Considerations

- **Secret and SSH mounts keep credentials out of layers**; `ARG`/`ENV` do not ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md), [§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Entitlements:** `network.host` and `security.insecure` (privileged `RUN`) are disabled by default and must be granted at builder level (`--allow`). Do not grant them to untrusted Dockerfiles.
- **Remote frontend trust:** `# syntax=` pulls and executes an image as part of the build. Pin by digest in sensitive pipelines (`# syntax=docker/dockerfile:1@sha256:...`).
- **Untrusted Dockerfiles:** a `RUN` executes arbitrary code on the builder. Use ephemeral, isolated, rootless builders for untrusted input; do not share a builder (and its cache) between trust levels.
- **Build context upload:** the client streams the context to the builder; `.dockerignore` keeps `.env`, keys and `.git` out ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).
- **Provenance** (`mode=max`) records build arguments and source details; review what it exposes before pushing to public registries.
- **Cache export** can leak intermediate stage contents ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `the --mount option requires BuildKit` | Legacy builder in use (`DOCKER_BUILDKIT=0`) | Remove the variable; use Engine 23+ or `buildx` |
| `unknown flag: --mount` / `Dockerfile parse error` | No `# syntax=` and an old frontend | Add `# syntax=docker/dockerfile:1` as the very first line |
| `failed to solve: failed to fetch ... docker/dockerfile` | Registry unreachable for the frontend image | Mirror the image, set a registry mirror, or drop the directive |
| Built image missing from `docker images` | `docker-container` driver without `--load` | Add `--load` or `--push` |
| `Cache export is not supported for the docker driver` | Default driver | Create a `docker-container` builder |
| `multiple platforms feature is currently not supported for docker driver` | Same | Same; use `--push` or an OCI/tar output for multi-platform |
| `secret "x" not found` | Missing `--secret id=x,...` at build time | Pass the secret, or mark `required=false` |
| `exec format error` in RUN on cross-build | Wrong stage platform | Use `--platform=$BUILDPLATFORM` for tooling stages |
| `insecure entitlement security.insecure is not allowed` | Needs builder permission | `--allow security.insecure` on builder creation (trusted use only) |

## 9. Best Practices

- Start every Dockerfile with `# syntax=docker/dockerfile:1`, pinned more tightly where reproducibility matters.
- Use mounts for caches, secrets and SSH instead of baking data into layers.
- Use heredocs for readable multi-line `RUN` and inline config files.
- Use `COPY --link` for final-stage artifact copies and `--chmod`/`--chown` instead of extra `RUN` layers.
- Run `docker buildx build --check` in CI to catch Dockerfile issues early.
- Prefer a `docker-container` builder with explicit GC policy for shared hosts.
- Use `--output type=local` to extract artifacts such as test reports or binaries without creating an image.
- Use `bake` for multi-image repos so targets, tags, cache and platforms live in version control.
- Generate SBOM and provenance attestations for released images.

## 10. Common Anti-Patterns / Mistakes

- Putting a comment or blank line above `# syntax=`, which silently disables it.
- Treating secrets as `ARG`/`ENV` when `--mount=type=secret` is available.
- Assuming the `docker` driver supports everything `docker-container` does.
- Granting `security.insecure` or `network.host` entitlements globally.
- Using the rolling `docker/dockerfile:1` tag in a release pipeline that demands exact reproducibility.
- Sharing one builder and cache between trusted and untrusted repositories.

## 11. Interview Questions

**🎯 Beginner:** _"What is BuildKit and how does a BuildKit build differ from the legacy builder?"_
**Model answer:** BuildKit is the build engine behind `docker build` today, the default since Docker Engine 23.0. Instead of executing instructions strictly one after another, it converts the Dockerfile into a dependency graph, runs independent stages in parallel, skips stages the target does not need, and caches by content. It also adds features like `RUN --mount` for caches and secrets, heredocs, and extra outputs such as exporting files to a directory. I would confirm it with `docker buildx ls` or the `#N [stage]` style progress output.
_What the interviewer is probing for:_ Basic awareness that BuildKit is the current default with parallelism and new Dockerfile features.

**🎯 Intermediate:** _"Explain what `# syntax=docker/dockerfile:1` does, and what can go wrong."_
**Model answer:** BuildKit separates the Dockerfile frontend from the daemon. The directive tells BuildKit to pull the named frontend image and use it to parse the Dockerfile into LLB, so new syntax such as heredocs or `COPY --link` works without upgrading dockerd. It must be the first line, before comments or blank lines. Risks: the build needs registry access to fetch the frontend (a problem in air-gapped builders), the rolling `:1` tag can change behavior over time, and it is code that executes in the build, so security-sensitive pipelines pin it by digest. The fix for reproducibility is `docker/dockerfile:1.x` or a digest pin.
_What the interviewer is probing for:_ Understanding the frontend abstraction and its operational implications.

**🎯 Senior:** _"A team needs to build a private-repo dependency with an SSH key and a package token, cache dependencies in CI, and produce amd64 and arm64 images with an SBOM. Walk me through the BuildKit features you would use."_
**Model answer:** Use `RUN --mount=type=ssh` for the git fetch and `RUN --mount=type=secret,id=npm_token` for the token, supplying them at build time with `--ssh default` and `--secret`, so nothing lands in a layer or in `docker history`. Add `--mount=type=cache` for the package manager and `--cache-from/--cache-to` to a registry or `gha` cache with `mode=max` on a `docker-container` builder. Build with `--platform linux/amd64,linux/arm64` using `--platform=$BUILDPLATFORM` for compile stages with `TARGETARCH` cross-compilation for speed, and `--push` with `--sbom=true --provenance=mode=max`. Verify with `docker buildx imagetools inspect` and scan the SBOM. I would also run `--check` in CI and keep the invocation in a `bake` file.
_What the interviewer is probing for:_ Combining mounts, remote cache, multi-platform and attestations coherently, and knowing driver constraints.

**🎯 Architect:** _"Design a company-wide build platform on BuildKit. What are the trust, scaling and governance decisions?"_
**Model answer:** Treat the builder as a code-execution service. Run ephemeral rootless BuildKit workers (Kubernetes driver or a managed service) with separate pools per trust tier so untrusted PR builds never share cache or credentials with release builds. Centralize configuration through `buildkitd.toml`: registry mirrors, GC policy, parallelism, and disabled entitlements by default. Provide blessed Dockerfile templates and a shared bake/CI workflow that enforce a pinned frontend digest, `--check` linting, secret and SSH mounts, cache refs, and SBOM and provenance generation, with signing downstream. Remote cache is read-write only from main, read-only elsewhere. Monitor build duration, queue time, cache hit rate and storage, and plan capacity and cost around them. Document an escape hatch process for teams needing entitlements, with review.
_What the interviewer is probing for:_ Systems thinking about isolation, shared cache trust, standardization and observability.

## 12. Common Misconceptions

- "`docker buildx` and `docker build` use different engines." Both use BuildKit now; buildx exposes more options and drivers.
- "Heredocs and mounts need a newer Docker daemon." They need the right frontend; `# syntax=` supplies it.
- "`--mount=type=secret` is like an env var." It is a tmpfs file or env only during that step and never persisted.
- "The default driver can do everything." Cache export, multi-platform and attestations generally need `docker-container` (or the containerd image store).
- "Cache mount contents ship in the image." They do not.

## 13. 🔑 Key Takeaways

- BuildKit = frontend ► LLB graph ► solver and worker ► exporter, with content-based caching and parallelism.
- Start Dockerfiles with `# syntax=docker/dockerfile:1`; it must be line 1.
- `RUN --mount` types: cache, bind, tmpfs, secret, ssh; none persist in the image.
- Heredocs, `COPY --link`, `--chmod`, `ADD --checksum` and `RUN --network=none` make Dockerfiles shorter and safer.
- Use a `docker-container` builder for cache export, multi-platform and attestations; add `--load` or `--push` to get results out.
- `--output type=local|tar|oci` builds artifacts without images; `--check` lints; `bake` orchestrates multiple targets.
- Entitlements, builder isolation and pinned frontends are the security levers.

## 14. Related Concepts & What's Next

Related: multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), caching ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), build basics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), multi-arch images ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)), supply chain ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), reproducible builds ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)). Next, [§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md) takes the `secret` and `ssh` mounts introduced here and shows how to use them safely, including what leaks when you do not.

**Next Section:** [§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md) — `Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md`
