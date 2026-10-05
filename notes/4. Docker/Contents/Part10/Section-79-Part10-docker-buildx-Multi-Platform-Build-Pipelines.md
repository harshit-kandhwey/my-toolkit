# Section 79 (Part 10): docker buildx: Multi-Platform Build Pipelines

## 1. Definition

**Plain language:** `docker buildx` is the Docker CLI front end to the full BuildKit engine. It lets you create and choose *builders*, build one Dockerfile for several CPU architectures (amd64, arm64, and others) in a single command, export results to a registry, a tarball or the local disk, share build cache between machines, and run many builds from one declarative file (`docker-bake.hcl`).

**Precise definition:** `buildx` is a CLI plugin (bundled with Docker Desktop and the Engine packages; `docker build` already uses it under the hood) that manages **builder instances** and drives BuildKit through them. A builder has one or more **nodes**, each with a **driver**:

| Driver | Where BuildKit runs | Multi-platform | Cache export | Typical use |
|---|---|---|---|---|
| `docker` | Inside dockerd | Only with the containerd image store | Limited (inline) | Default, local dev |
| `docker-container` | A dedicated BuildKit container | Yes | All backends | CI and anywhere you need full features |
| `kubernetes` | BuildKit pods in a cluster | Yes, per-arch node pools | All backends | Shared in-cluster builders |
| `remote` | An existing buildkitd endpoint | Yes | All backends | Dedicated build servers, cloud builders |

A **multi-platform image** is an OCI image index (manifest list) that points to one image manifest per platform ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md), [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). `buildx` builds each platform, then assembles and pushes the index.

> 💡 **Tip:** `--platform` takes a comma-separated list: `--platform linux/amd64,linux/arm64`. The result of a multi-platform build cannot be loaded into the classic local image store as one image; push it, or export it as OCI.

## 2. Why This Matters

- Teams now deploy to a mix of x86 servers, Graviton or Ampere ARM instances, and Apple Silicon laptops. One tag that works everywhere removes "exec format error" incidents.
- The way you produce each platform (emulation, native nodes, or cross-compilation) changes build times by 10x or more.
- A pipeline built on `buildx` and bake is the standard way to get provenance, SBOMs, remote cache and multiple tags from a single, reviewable definition ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)).
- It is the bridge from local builds to CI/CD ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)).

## 3. Prerequisites and Dependencies

Requires the BuildKit model ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md), [§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), cache invalidation ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), and manifest lists plus registry push ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md), [§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)). Registry login is covered in [§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md). For emulated builds the host needs QEMU user-mode emulation registered through `binfmt_misc` (kernel feature, see [§5](../Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md)). Image size techniques ([§77](Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)) multiply across platforms.

## 4. Architecture / Conceptual Diagram

```text
  docker buildx build --platform linux/amd64,linux/arm64 --push -t reg/app:1.4.2 .
        │
        ▼
  ┌──────────────────── builder "ci" (driver: docker-container) ────────────────────┐
  │   BuildKit solver: one LLB graph, solved once per target platform               │
  │                                                                                 │
  │   linux/amd64 branch              linux/arm64 branch                            │
  │   ┌─────────────────┐             ┌──────────────────────────────┐              │
  │   │ native node     │             │ strategy A: QEMU emulation   │ (slow)       │
  │   │ (amd64 host)    │             │ strategy B: native arm64 node│ (fast)       │
  │   └────────┬────────┘             │ strategy C: cross-compile on │ (fast)       │
  │            │                      │   $BUILDPLATFORM, TARGETARCH │              │
  │            ▼                      └───────────────┬──────────────┘              │
  │     image manifest (amd64)               image manifest (arm64)                 │
  └───────────────────┬─────────────────────────────┬───────────────────────────────┘
                      └──────────────┬──────────────┘
                                     ▼
                  OCI image index  reg/app:1.4.2  ──► registry
                  ├─ linux/amd64 → sha256:aaa...
                  ├─ linux/arm64 → sha256:bbb...
                  └─ attestation manifests (provenance, SBOM) tagged unknown/unknown

  Cache:   --cache-from type=registry,ref=reg/app:buildcache  ◄── shared by all runners
           --cache-to   type=registry,ref=reg/app:buildcache,mode=max  ──►
```

- **Build-platform vs target-platform:** `BUILDPLATFORM` is where the build step runs; `TARGETPLATFORM` is what the image is for. Cross-compilation pins a stage to `--platform=$BUILDPLATFORM` so it always runs natively and only the output differs.
- **Automatic args:** BuildKit exposes `TARGETPLATFORM`, `TARGETOS`, `TARGETARCH`, `TARGETVARIANT`, `BUILDPLATFORM` and friends as predefined `ARG`s; declare them inside a stage (`ARG TARGETARCH`) to use them ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).

## 5. Hands-On

### 5.1 Create and Inspect a Builder

```bash
docker buildx ls
docker buildx create --name ci --driver docker-container --bootstrap --use
docker buildx inspect ci
```

```text
NAME/NODE      DRIVER/ENDPOINT   STATUS    PLATFORMS
default*       docker
  default      default           running   linux/amd64, linux/amd64/v2, linux/386
ci             docker-container
  ci0          unix:///var/run/docker.sock  running  linux/amd64, linux/amd64/v2, linux/amd64/v3, linux/386
```

The `PLATFORMS` column shows what the node can build; emulated platforms appear only once QEMU binfmt handlers are registered (`docker run --privileged --rm tonistiigi/binfmt --install arm64`; in GitHub Actions use `docker/setup-qemu-action`). The builder runs as a container named `buildx_buildkit_ci0` with its own cache volume. Use `docker buildx rm ci` to remove it, and `docker buildx du` / `docker buildx prune` to manage its cache ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).

### 5.2 First Multi-Platform Build

```dockerfile
# syntax=docker/dockerfile:1
FROM alpine:3.20
ARG TARGETPLATFORM
RUN echo "built for $TARGETPLATFORM on $(uname -m)" > /info
CMD ["cat", "/info"]
```

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t reg.example.com/demo/info:1 --push .
docker buildx imagetools inspect reg.example.com/demo/info:1
docker run --rm --platform linux/arm64 reg.example.com/demo/info:1
```

```text
Name:      reg.example.com/demo/info:1
MediaType: application/vnd.oci.image.index.v1+json
Manifests:
  Platform:  linux/amd64
  Platform:  linux/arm64
built for linux/arm64 on aarch64
```

Without `--push`, `--load` (single platform) or `--output`, a `docker-container` build leaves the result only in build cache.

### 5.3 Cross-Compile Instead of Emulate (Go Example)

```dockerfile
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM golang:1.23 AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags="-s -w" -o /out/app ./cmd/app

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/app /app
ENTRYPOINT ["/app"]
```

The `build` stage always runs on the native build host, so the compiler runs at full speed while emitting the target architecture binary; only trivial `COPY` steps happen per platform. The same pattern works for Rust (`--target`), .NET (`-r linux-$TARGETARCH`) and Java/Node (architecture-neutral artifacts, with per-arch native dependencies the only concern). Emulation (QEMU) is the fallback for steps that must execute target binaries, such as `apt-get install` in a target-arch base, and is commonly 5x to 20x slower.

### 5.4 Shared Cache Across Runners

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --cache-from type=registry,ref=reg.example.com/app:buildcache \
  --cache-to   type=registry,ref=reg.example.com/app:buildcache,mode=max,image-manifest=true \
  -t reg.example.com/app:1.4.2 --push .
```

`mode=max` exports every intermediate layer, not just the final image's, which is what multi-stage builds need to hit the cache. Other backends: `type=gha` (GitHub Actions cache service), `type=s3`, `type=azblob`, `type=local,dest=./cache`, and `type=inline` (embeds cache in the pushed image, `min` mode only). CI-specific tradeoffs continue in [§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md).

### 5.5 Attestations: SBOM and Provenance

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  --sbom=true --provenance=mode=max \
  -t reg.example.com/app:1.4.2 --push .
docker buildx imagetools inspect reg.example.com/app:1.4.2 --format '{{ json .SBOM }}' | head -c 300
```

Attestations are stored as extra manifests in the index (platform `unknown/unknown`) and are generated per platform. Pull-time tooling ignores them, but scanners and policy engines consume them ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md), [§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Some registries and old tooling mishandle `unknown/unknown` entries; set `--provenance=false --sbom=false` only after confirming that is the cause.

### 5.6 Bake: The Pipeline as a File

```hcl
# docker-bake.hcl
variable "VERSION" { default = "dev" }
variable "REGISTRY" { default = "reg.example.com/team" }

group "default" { targets = ["app"] }

target "_common" {
  dockerfile = "Dockerfile"
  platforms  = ["linux/amd64", "linux/arm64"]
  args       = { SOURCE_DATE_EPOCH = "0" }
  attest     = ["type=sbom", "type=provenance,mode=max"]
  cache-from = ["type=registry,ref=${REGISTRY}/app:buildcache"]
  cache-to   = ["type=registry,ref=${REGISTRY}/app:buildcache,mode=max"]
}

target "app" {
  inherits = ["_common"]
  tags     = ["${REGISTRY}/app:${VERSION}", "${REGISTRY}/app:latest"]
  output   = ["type=registry"]
}

target "app-local" {              # fast single-platform dev build
  inherits  = ["app"]
  platforms = ["linux/amd64"]
  output    = ["type=docker"]
  tags      = ["app:dev"]
}
```

```bash
docker buildx bake --print app          # show the resolved build definition (dry run)
VERSION=1.4.2 docker buildx bake app    # build and push everything
docker buildx bake app-local            # local dev variant
```

Bake can also load a Compose file (`docker buildx bake -f compose.yaml`). The same file runs locally and in CI, which removes a whole class of "works in the pipeline only" drift.

## 6. Production Usage Notes

- **Choose a strategy per language:** compiled languages with good cross-compilers (Go, Rust, .NET) should cross-compile on `$BUILDPLATFORM`; interpreted stacks with native extensions (Python wheels, Node addons) usually need native arm64 runners or accept emulation cost.
- **Prefer native runners** when available (GitHub-hosted arm64 runners, Graviton CI agents). They also avoid QEMU quirks such as segfaults in JIT-heavy runtimes and occasional `illegal instruction` errors.
- **Pin the builder:** `--driver-opt image=moby/buildkit:v0.17.0` (use a version you have tested) keeps builds identical across runners. `network=host` and `env.http_proxy` driver options handle restricted networks.
- **Retention:** lifecycle rules must not delete untagged per-platform manifests an index references ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- **Test every platform you ship:** run the image under `--platform` (QEMU on the host) in CI smoke tests, or on real nodes for performance-sensitive code.

## 7. Security Considerations

- **`tonistiigi/binfmt --install` runs privileged** and changes host kernel handlers. Restrict it to dedicated, ephemeral build hosts, and never on shared developer or production machines.
- **The `docker-container` driver runs BuildKit as a privileged container** by default (needed for its sandbox). Treat the builder like a root-equivalent service; do not expose its socket, and avoid sharing one builder between untrusted tenants. Consider rootless BuildKit or a `kubernetes` driver with hardened pod security for multi-tenant CI.
- **Registry credentials** used for `--push` and cache export should be short-lived tokens or credential helpers ([§69](../Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)). A registry cache ref contains layer contents, so restrict its repository like the image itself; do not publish `mode=max` cache to a public repo if build stages ever touched sensitive material.
- **Build secrets** must use `--secret` mounts, not args, and cache export does not store mounted secrets ([§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Remote builders over SSH or TCP:** use SSH or mutual TLS; an unauthenticated buildkitd TCP endpoint is remote code execution.
- **Attest what you ship:** keep provenance on release builds and sign the index digest, not a per-platform digest ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `multiple platforms feature is currently not supported for docker driver` | Using the default `docker` driver without the containerd image store | Create a `docker-container` builder or enable the containerd store |
| `exec /bin/sh: exec format error` during build | Target platform not emulated (binfmt missing) | Install QEMU handlers (`tonistiigi/binfmt --install all`) or use a native node |
| `docker exec format error` at runtime on a server | Image has no manifest for the host architecture | `imagetools inspect`; add the platform to `--platform` |
| Build is extremely slow for arm64 | QEMU emulation of compilers and package managers | Cross-compile on `$BUILDPLATFORM` or add a native arm64 node |
| Built image not found by `docker images` | Result stayed in builder cache | Add `--load` (single platform) or `--push` or `--output` |
| `--load` fails with multiple platforms | Classic store holds one image per tag | Push, export OCI, or enable the containerd store |
| Cache never hits in CI | Fresh builder per job and no `--cache-from` | Add registry/gha cache with `mode=max`; keep cache refs consistent |

## 9. Best Practices

- Use a `docker-container` (or remote/Kubernetes) builder for anything beyond local experiments.
- Cross-compile with `--platform=$BUILDPLATFORM` stages wherever the toolchain allows.
- Prefer native runners over QEMU for slow or sensitive builds.
- Define the pipeline in `docker-bake.hcl` and use `bake --print` as a review artifact.
- Export cache with `mode=max` to a registry or the CI cache service, and name cache refs predictably.
- Always declare automatic platform ARGs inside the stages that use them.
- Produce SBOM and provenance on release builds; sign the index digest.
- Pin the BuildKit image version and `# syntax=` frontend for repeatable pipelines ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)).

## 10. Common Anti-Patterns / Mistakes

- Building arm64 under QEMU for a large C++ or Rust project when cross-compilation or a native runner is available.
- Pushing `app:latest` from each architecture's job separately, so the last writer wins and the tag points to one platform.
- Leaving `tonistiigi/binfmt` installs on shared, long-lived developer hosts.
- Exposing a buildkitd TCP port without TLS.

## 11. Interview Questions

**🎯 Beginner:** _"What does `docker buildx build --platform linux/amd64,linux/arm64 --push` produce, and why can't you just `--load` it?"_
**Model answer:** It builds the Dockerfile once per platform and pushes an OCI image index (manifest list) that references one image manifest per architecture. When a client pulls the tag, the runtime selects the manifest matching its platform. `--load` imports into the local image store, which in the classic store holds a single-platform image per tag, so it cannot hold an index; use `--push`, an OCI/tar export, or the containerd image store. You also need a builder that supports multi-platform builds, such as the `docker-container` driver, rather than the default `docker` driver on the classic store.
_What the interviewer is probing for:_ Understanding of manifest lists and where build output goes.

**🎯 Intermediate:** _"An arm64 build of your Python service takes 40 minutes in CI but the amd64 build takes 4. What are your options?"_
**Model answer:** The arm64 leg is running under QEMU, and compiling wheels or installing packages in emulation is slow. Options in order of preference: build arm64 on a native arm64 runner (a multi-node builder or per-arch jobs stitched with `imagetools create`); use pure-Python or prebuilt wheels so there is little to compile; move compilation into a `--platform=$BUILDPLATFORM` stage and copy only artifacts if the language cross-compiles; and add registry cache with `mode=max` so unchanged layers are not rebuilt. QEMU remains acceptable for tiny steps. I would measure per-step time with the build progress output or `--progress=plain` before choosing.
_What the interviewer is probing for:_ Distinguishing emulation, native and cross-compilation strategies, and cache.

**🎯 Senior:** _"Explain `BUILDPLATFORM`, `TARGETPLATFORM` and how a Dockerfile cross-compiles a Go binary for arm64 on an amd64 runner."_
**Model answer:** `BUILDPLATFORM` is the platform of the machine executing the build; `TARGETPLATFORM` (with `TARGETOS`, `TARGETARCH`, `TARGETVARIANT`) is the platform of the image being produced. The compile stage is declared `FROM --platform=$BUILDPLATFORM golang`, so it runs natively with no emulation, and uses `ARG TARGETOS TARGETARCH` to set `GOOS`/`GOARCH` and emit a target binary. The final stage has no platform override, so it resolves to the target platform's base image, and the binary is copied in. The cost is that only steps needing to run target code are emulated, and with a static binary on distroless there are none. These automatic args must be declared in each stage that uses them.
_What the interviewer is probing for:_ Mastery of platform ARGs and per-stage platform pinning.

**🎯 Architect:** _"Design a multi-platform build and release pipeline for 50 services with remote cache, attestations and a requirement that arm64 deploys never differ in source from amd64."_
**Model answer:** Standardise on a shared bake file (inherited by each service) that defines platforms, cache refs, attestations and tags, executed by CI on a pool of ephemeral `docker-container` builders, with native amd64 and arm64 nodes registered in one multi-node builder (or per-arch jobs plus `imagetools create`). A single build invocation produces the index, so both architectures come from the same commit and Dockerfile solve; pin the BuildKit image, frontend and base digests. Registry cache per service with `mode=max` and retention rules that protect cache and per-platform manifests. Generate SBOM and max provenance, sign the index digest, and have the deploy system pull by digest. Post-build gates: `imagetools inspect` confirms the expected platform set, per-arch smoke tests run on native nodes, and a policy engine verifies signatures and provenance before promotion. Builders are isolated per tenant or run rootless, and binfmt installation is confined to the builder image or hosts.
_What the interviewer is probing for:_ End-to-end design: builder topology, cache, supply-chain, governance and failure modes.

## 12. Common Misconceptions

- "`docker build` and `docker buildx build` are different engines." Both use BuildKit; buildx exposes more features (builders, multi-platform, cache backends, bake).
- "A multi-platform tag is one big image." It is an index pointing to separate per-platform images.
- "`--cache-to type=inline` is as good as registry cache." Inline supports only final-image layers (`min` mode); multi-stage builds need `mode=max` via a cache backend.

## 13. 🔑 Key Takeaways

- `buildx` is the full BuildKit CLI: builders, drivers, multi-platform output, cache backends, attestations, bake.
- Multi-platform builds produce an OCI index; push it or export it rather than `--load`.
- Fastest to slowest: cross-compile on `$BUILDPLATFORM`, native nodes per arch, QEMU emulation.
- Declare `TARGETARCH` and friends with `ARG` in each stage that needs them.
- Share cache with `--cache-from/--cache-to` (`mode=max`) via registry or CI cache.
- Describe the pipeline in `docker-bake.hcl` so local and CI builds match.
- Treat builders, binfmt installs and cache refs as privileged infrastructure.

## 14. Related Concepts & What's Next

Related: manifest lists ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)), OCI image spec ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), cache strategies ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), BuildKit syntax ([§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), reproducibility ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)). This closes Part 10 on building images well. Part 11 moves these builds into automation, starting with how GitHub Actions, GitLab CI and Jenkins run Docker builds ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md)).

**Next Section:** [§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md) — `Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md`
