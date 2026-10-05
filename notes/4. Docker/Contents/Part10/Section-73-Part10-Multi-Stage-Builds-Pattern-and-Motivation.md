# Section 73 (Part 10): Multi-Stage Builds: Pattern and Motivation

## 1. Definition

**Plain language:** A multi-stage build uses several `FROM` lines in one Dockerfile. Early stages have the compilers and tools needed to build your software; the last stage is a small, clean image into which you copy only the finished output. The build tools never ship.

**Precise definition:** Each `FROM` starts a new *stage* with its own filesystem and layers. Stages can be named (`FROM golang:1.23 AS build`) and referenced with `COPY --from=<name|index>` or as a base (`FROM build AS test`). Only the stage you target (by default the last) becomes the resulting image; other stages exist only in the build cache. With BuildKit ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)) the stage graph is solved as a DAG: independent stages build in parallel, and stages not needed by the target are skipped entirely. `COPY --from` can also copy from an external image (`COPY --from=nginx:1.27 /etc/nginx/nginx.conf /`).

> 💡 **Tip:** Multi-stage replaced the old "builder pattern" (two Dockerfiles plus a shell script to `docker cp` artifacts between them).

## 2. Why This Matters

- Smaller images pull faster, start faster and cost less to store and transfer ([§77](Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)); a Go service can drop from ~900 MB to under 20 MB.
- Fewer packages means a smaller attack surface and fewer scanner findings: no compiler, package manager caches, git or test frameworks in production ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- Build secrets, source history and private tokens used during compilation stay out of the final layers ([§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- One Dockerfile can define dev, test and prod variants through named stages, keeping them consistent.
- It is a staple of Dockerfile reviews and interviews, and a prerequisite for distroless and `scratch` images ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)).

## 3. Prerequisites and Dependencies

Requires Dockerfile fundamentals ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), image layers ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `ARG` and `ENV` scoping ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), base image choices ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)) and `docker build` with BuildKit ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)). It pairs closely with cache design ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)) and BuildKit features ([§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)). Tools such as `dive` ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)) verify what ended up in the final image.

## 4. Architecture / Conceptual Diagram

```text
  Dockerfile                                   Build graph (BuildKit)

  FROM node:22 AS deps       ──────────┐
  FROM node:22 AS build  ◄─ COPY --from=deps  (node_modules)
  FROM build   AS test                 │        ▲
  FROM nginx:1.27-alpine AS runtime ◄──┘        │
        ▲   COPY --from=build /app/dist         │
        │                                        │
   default target = last stage             test stage runs only
   (what you ship)                         with --target test

  What ends up where
  ┌──────────────┬───────────────────────────────┬──────────────┐
  │ Stage        │ Contents                      │ Shipped?     │
  ├──────────────┼───────────────────────────────┼──────────────┤
  │ deps         │ package.json, node_modules    │ no (cache)   │
  │ build        │ source, dev deps, toolchain   │ no (cache)   │
  │ test         │ build + test runner           │ no           │
  │ runtime      │ nginx + compiled static files │ YES          │
  └──────────────┴───────────────────────────────┴──────────────┘
```

- **Stages are isolated:** nothing carries over except what you explicitly `COPY --from`. `ENV` and `WORKDIR` do not leak between stages.
- **The build cache keeps non-final stages,** so a later rebuild can reuse them even though they were never shipped.
- **Order of stages is not order of execution:** BuildKit builds only what the target depends on, concurrently where possible.
- **`ARG` before the first `FROM`** is global to `FROM` lines only; redeclare `ARG NAME` inside a stage to use it there.

## 5. Hands-On

### 5.1 Single Stage: The Problem

```dockerfile
FROM golang:1.23
WORKDIR /src
COPY . .
RUN go build -o /usr/local/bin/app .
CMD ["app"]
```

```bash
docker build -t app:single .
docker images app:single
```

```text
REPOSITORY   TAG      IMAGE ID       CREATED          SIZE
app          single   3b1f0c9a2d11   10 seconds ago   868MB
```

The image carries the Go toolchain, source code, module cache and a full Debian userland.

### 5.2 Two Stages: Compile, Then Copy

```dockerfile
FROM golang:1.23 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/app .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/app /app
ENTRYPOINT ["/app"]
```

```bash
docker build -t app:multi .
docker images app:multi
```

```text
REPOSITORY   TAG     IMAGE ID       CREATED         SIZE
app          multi   8e41d7a6b0c3   5 seconds ago   9.6MB
```

`CGO_ENABLED=0` yields a static binary that runs on `static` distroless or `scratch`. The `:nonroot` tag runs as UID 65532 ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)).

### 5.3 Interpreted Language: Build Dependencies Away from Runtime

```dockerfile
FROM python:3.12 AS build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim AS runtime
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY . .
USER 10001
CMD ["python", "-m", "app"]
```

The build stage may include `gcc` and headers (`python:3.12` full image) to compile wheels; only the resulting virtualenv is copied into the slim runtime. The Python minor version and libc must match between stages.

### 5.4 Named Stages for Dev, Test and Prod

```dockerfile
FROM node:22-alpine AS base
WORKDIR /app
COPY package*.json ./

FROM base AS dev
RUN npm ci
COPY . .
CMD ["npm", "run", "dev"]

FROM base AS build
RUN npm ci
COPY . .
RUN npm run build

FROM build AS test
RUN npm test

FROM nginx:1.27-alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
```

```bash
docker build --target dev  -t web:dev  .
docker build --target test -t web:test .
docker build                -t web:prod .
```

`--target` stops the build at that stage. With BuildKit, the default build (`prod`) never runs the `dev` or `test` stages because nothing depends on them. To make tests a gate, make the final stage depend on them (for example `COPY --from=test /app/.ok /dev/null`) or run the `test` target as a separate CI step.

### 5.5 Copy from an External Image

```dockerfile
FROM alpine:3.20
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
COPY --from=busybox:1.37 /bin/busybox /bin/busybox
```

This pulls single files from published images without installing packages, a common way to add `tini`, `uv` or `grpc_health_probe`.

### 5.6 Passing Build Information Between Stages

```dockerfile
FROM alpine:3.20 AS version
ARG GIT_SHA=unknown
RUN echo "$GIT_SHA" > /version

FROM alpine:3.20
COPY --from=version /version /etc/app-version
```

```bash
docker build --build-arg GIT_SHA=$(git rev-parse --short HEAD) -t app:1 .
docker run --rm app:1 cat /etc/app-version
```

```text
a1b2c3d
```

Because `ARG` values are stored in image history only for the stage where they are used, keeping them in a throwaway stage keeps them out of the final image's history.

### 5.7 Verify What You Shipped

```bash
docker history app:multi
docker run --rm app:multi /app --version
dive app:multi
```

```text
IMAGE          CREATED BY                         SIZE
8e41d7a6b0c3   ENTRYPOINT ["/app"]                0B
<missing>      COPY /out/app /app # buildkit      6.1MB
<missing>      (distroless base layers)           3.5MB
```

Only the base layers and one application layer appear; the `build` stage's history is not part of the image.

## 6. Production Usage Notes

- **Order stages for cache efficiency:** put dependency manifests and downloads before source copy ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).
- **Pin base images** (tag plus digest) for every stage, including the build stage, for repeatable results ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)).
- **Use `--target` in CI** for test, lint and security-scan stages; ship the default target.
- **Share a `base` stage** for common OS packages and users across services in a repo to keep layers identical.
- **Run as non-root in the final stage** and create any required writable directories with correct ownership there.
- **Remember runtime dependencies:** dynamically linked binaries need the same libc (glibc vs musl) in the final stage; mismatches show as `not found` for a file that exists.
- **Copy certificates and timezone data** into `scratch` images (`/etc/ssl/certs/ca-certificates.crt`, `/usr/share/zoneinfo`).
- **Multi-platform builds** combine naturally with `FROM --platform=$BUILDPLATFORM` for the build stage ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md), [§79](Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)).

## 7. Security Considerations

- **Final image minimalism:** removing shells, package managers and compilers raises the cost of post-exploitation and reduces CVE counts ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md), [§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Secrets in earlier stages are not automatically safe.** They are absent from the shipped image, but they live in the local build cache, and if you push cache (`--cache-to`) they travel to the registry. Use `RUN --mount=type=secret` instead of `COPY .npmrc` or `ARG TOKEN` ([§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Never `COPY --from=build /src /app`** wholesale: that brings in `.git`, test fixtures, and any stray credentials. Copy only named outputs.
- **Scan the final image,** and scan the build stage's base separately if build tooling processes untrusted input.
- **Supply chain:** build-stage base images and downloaded tools are part of your trust chain; pin and verify them ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Copying from external images** (`COPY --from=vendor/tool`) trusts that image; pin by digest.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `exec /app: no such file or directory` though the file exists | Dynamically linked binary (glibc) on `scratch`/alpine (musl) | Build static (`CGO_ENABLED=0`) or match libc between stages |
| `COPY --from=build` fails: `file not found` | Wrong path or the artifact was written in another `WORKDIR` | Use absolute paths; verify with `docker build --target build` and `ls` |
| `failed to solve: invalid from flag value` / unknown stage | Typo in stage name or stage defined after use | Check `AS` names (case-insensitive) and order |
| Tests never run during `docker build` | Test stage not required by the final stage (BuildKit skips it) | Build with `--target test`, or make the final stage depend on it |
| `ARG` is empty inside a stage | `ARG` declared before first `FROM` and not redeclared | Add `ARG NAME` inside the stage |
| Final image still huge | Copied the whole build tree, or final `FROM` is the build image | Copy only artifacts; use a slim/distroless base |
| Python module import errors at runtime | Wheels built against different Python/libc than runtime stage | Use same minor version and compatible OS family |
| Missing HTTPS roots / timezone in `scratch` | Nothing provides CA bundle or tzdata | Copy `ca-certificates.crt` and zoneinfo from build stage |
| `permission denied` running copied binary | Lost executable bit or wrong owner | `COPY --chmod=755 --chown=10001:10001 --from=build ...` |

## 9. Best Practices

- Name every stage (`AS build`) and refer to stages by name, not number.
- Keep the last stage the shipping target and make it as small as the app allows.
- Copy dependency manifests first, install, then copy source ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).
- Add `test`, `lint` and `dev` stages for the same Dockerfile and select with `--target`.
- Use `--chown` and `--chmod` on `COPY --from` instead of extra `RUN chown` layers.
- Build static binaries when using `scratch` or distroless `static`.
- Verify the result with `docker history`, `dive` and a scan ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)).
- Set `# syntax=docker/dockerfile:1` at the top to get current Dockerfile features ([§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)).

## 10. Common Anti-Patterns / Mistakes

- A "multi-stage" Dockerfile whose final stage is `FROM build`, shipping everything anyway.
- Copying the entire source tree or `node_modules` with dev dependencies into the runtime stage.
- Installing build tools in the runtime stage and removing them with `RUN apt-get purge` (the layers still exist; use separate stages).
- Passing secrets via `ARG` or `COPY` in the build stage and assuming multi-stage makes that safe.
- Using unpinned `latest` build images so rebuilds change silently.
- Duplicating the same long `RUN apt-get install` across stages instead of a shared `base` stage.
- Relying on stage order rather than explicit dependencies to force tests to run.
- Assuming `ENV` and `USER` set in the build stage apply to the final image.

## 11. Interview Questions

**🎯 Beginner:** _"What is a multi-stage build and what problem does it solve?"_
**Model answer:** It is a Dockerfile with more than one `FROM`. Each `FROM` starts a new stage; I compile or install dependencies in an early stage that has the toolchain, then start a clean final stage and use `COPY --from=build` to bring in only the finished artifact. The final image does not contain the compiler, source code or package caches, so it is smaller, faster to pull and has less attack surface. It replaces the older builder pattern with separate Dockerfiles and scripts.
_What the interviewer is probing for:_ Basic mechanics (`AS`, `COPY --from`) and the size/security motivation.

**🎯 Intermediate:** _"You added a `test` stage to your Dockerfile, but a normal `docker build` never runs the tests. Why, and how do you run them?"_
**Model answer:** BuildKit solves only the stages the target depends on. The final stage does not reference `test`, so it is skipped. Run it explicitly with `docker build --target test .` as a CI step before building the production target, or make the production stage consume something from the test stage so it becomes a dependency. I prefer the explicit `--target test` step because it keeps the shipping graph minimal and surfaces test output and failures separately, and cached results are reused by the later build of the same base stages.
_What the interviewer is probing for:_ Understanding BuildKit's dependency-driven execution and `--target`.

**🎯 Senior:** _"Your Go multi-stage image works locally but the container dies with `exec /app: no such file or directory`. The binary is clearly in the image. What is going on?"_
**Model answer:** That message usually refers to the ELF interpreter, not the file. The binary was built in a glibc-based `golang` image with cgo enabled (the default when a C toolchain is present), so it is dynamically linked against `/lib64/ld-linux-x86-64.so.2`, which does not exist in `scratch`, distroless `static` or musl-based alpine. Verify with `ldd` or `file` in the build stage. Fix by building static with `CGO_ENABLED=0` (and `-tags netgo` if needed), or keep cgo and use a runtime image with the matching libc, such as `distroless/base` or the same Debian release. Then add a CI smoke test that runs the final image.
_What the interviewer is probing for:_ Debugging static vs dynamic linking and runtime/base image compatibility.

**🎯 Architect:** _"Design a standard multi-stage Dockerfile strategy for 80 services across Go, Java, Node and Python."_
**Model answer:** Provide per-language Dockerfile templates with a common shape: a pinned `base` stage, `deps` (manifest-only copy and install for cache hits), `build`, `test`, optionally `dev`, and a minimal `runtime` (distroless or slim, non-root, read-only-friendly). Enforce rules in CI with a Dockerfile linter (hadolint) and policy checks: digest-pinned bases, no secrets via `ARG`/`COPY`, a non-root `USER`, and image size budgets. Use BuildKit cache mounts and a shared remote cache to keep builds fast, build with `--target` per pipeline phase, and produce SBOMs and signatures on the final image only. Publish a base-image catalog maintained by the platform team and rebuilt on CVE updates, so services inherit patches by rebuilding rather than editing Dockerfiles. Track outcomes with metrics: image size, build time, critical CVE count per service.
_What the interviewer is probing for:_ Standardization, governance and measurable outcomes beyond the syntax.

## 12. Common Misconceptions

- "Multi-stage builds make secrets safe." Secrets are only absent from the final layers; the cache and any exported cache still hold them unless secret mounts are used.
- "Every stage runs on every build." BuildKit builds only the stages the target needs.
- "Stages share environment variables and working directories." Each stage starts fresh from its own `FROM`.
- "Multi-stage is only for compiled languages." It also isolates build dependencies for Python, Node and Java, and bundles front-end assets.
- "More stages means a bigger image." Only the final stage's layers ship.
- "`COPY --from` only works with stages in the same file." It can also copy from any image reference.

## 13. 🔑 Key Takeaways

- Multiple `FROM` lines create stages; only the target stage becomes the image.
- Build in a tool-rich stage, copy only artifacts into a minimal final stage.
- `COPY --from=<stage|image>` is the only bridge; stages do not share `ENV` or `WORKDIR`.
- BuildKit skips unneeded stages and parallelizes independent ones; use `--target` for test and dev.
- Static binaries plus distroless or `scratch` give the smallest, safest results; match libc otherwise.
- Do not treat earlier stages as a secret store; use secret mounts.

## 14. Related Concepts & What's Next

Related: Dockerfile fundamentals ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), base image selection ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)), BuildKit basics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), multi-arch cross-compilation ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)), size techniques ([§77](Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)). Next, [§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md) explains how layer caching and invalidation determine how fast these stages rebuild.

**Next Section:** [§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md) — `Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md`
