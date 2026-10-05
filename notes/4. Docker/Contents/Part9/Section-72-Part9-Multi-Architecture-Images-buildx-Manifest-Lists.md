# Section 72 (Part 9): Multi-Architecture Images: buildx, Manifest Lists

## 1. Definition

**Plain language:** A multi-architecture image is one image name and tag (for example `myorg/app:1.4.2`) that works on both Intel/AMD servers and ARM machines (Apple Silicon laptops, AWS Graviton). The registry holds one build per platform and hands each client the right one automatically.

**Precise definition:** A *platform* is an `os/architecture[/variant]` triple such as `linux/amd64`, `linux/arm64` or `linux/arm/v7`. A multi-platform image is an **OCI image index** (Docker's older equivalent is a **manifest list**, media type `application/vnd.docker.distribution.manifest.list.v2+json`): a small JSON document whose entries each point, by digest, to a platform-specific image manifest ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md), [§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). When a client pulls the tag, the registry returns the index, and the client selects the entry matching its own platform (or the one requested with `--platform`). `docker buildx` is the CLI plugin that drives BuildKit and can build for several platforms in one invocation and push the resulting index.

> 💡 **Tip:** The tag points to the *index digest*. Each platform image has its own, different digest. Pin by index digest to stay multi-arch; pin by platform digest to lock one architecture.

## 2. Why This Matters

- ARM is mainstream: Apple Silicon developer machines, AWS Graviton and other ARM cloud instances cost less per unit of work, and Raspberry Pi/edge fleets are ARM.
- An amd64-only image on an ARM host either fails with `exec format error` or runs slowly under emulation; an arm64-only image fails the same way on amd64.
- One tag for all platforms keeps Compose files, Helm charts and pipelines free of per-architecture branching.
- Building on a laptop (arm64) for a production cluster (amd64) is a very common source of "works on my machine" breakage, and an interview favorite.
- Mixed-architecture clusters (Graviton migration in progress) require images that schedule on either node type.

## 3. Prerequisites and Dependencies

Requires image anatomy and manifests ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), the OCI specs ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)), `docker build` and BuildKit basics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), and push/pull and tagging ([§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)). Registry authentication ([§69](Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)) is needed to push, and the registry must support OCI indexes (Docker Hub, ECR, ACR, Artifact Registry and Harbor all do; see [§66](Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md), [§67](Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md), [§68](Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)). The deeper pipeline view is in [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md). Emulation relies on QEMU user-mode and the kernel `binfmt_misc` facility.

## 4. Architecture / Conceptual Diagram

```text
  Registry: myorg/app:1.4.2   (tag ──► image index)
  ┌───────────────────────────────────────────────────────────┐
  │ Image index  sha256:AAAA...                               │
  │  manifests:                                               │
  │   ├─ platform linux/amd64  ──► manifest sha256:1111...    │
  │   ├─ platform linux/arm64  ──► manifest sha256:2222...    │
  │   └─ platform linux/arm/v7 ──► manifest sha256:3333...    │
  └───────────────────────────────────────────────────────────┘
        ▲                  ▲                     ▲
        │ pull on amd64    │ pull on arm64       │ pull on armv7
   client picks 1111   client picks 2222     client picks 3333
   (config + layers)   (config + layers)     (config + layers)

  Three ways buildx produces each platform image
  ┌───────────────┬──────────────────────────┬───────────────────────┐
  │ QEMU emulation│ Native builder nodes     │ Cross-compile in      │
  │ (binfmt_misc) │ (one builder, N nodes)   │ Dockerfile            │
  ├───────────────┼──────────────────────────┼───────────────────────┤
  │ Easy, slow    │ Fast, needs ARM+x86 hosts│ Fastest, needs        │
  │ 5-20x slower  │ or cloud runners         │ toolchain support     │
  └───────────────┴──────────────────────────┴───────────────────────┘
```

- **Index vs manifest:** the index is a list of pointers; layers and config live in the per-platform manifests.
- **Layer sharing:** architecture-independent layers (for example copied static files) have the same digest and are stored once.
- **Builder drivers:** the default `docker` driver builds one platform into the local image store; the `docker-container` driver (a BuildKit container) is needed for multi-platform output. Docker Engine 27/28 with the containerd image store can also hold multi-platform images locally.
- **Attestations:** modern BuildKit adds provenance and SBOM attestation manifests to the index, shown as `unknown/unknown` platform entries; they are not runnable images.

## 5. Hands-On

### 5.1 See What Platform You Are On

```bash
docker version --format '{{.Server.Os}}/{{.Server.Arch}}'
docker run --rm alpine:3.20 uname -m
```

```text
linux/arm64
aarch64
```

### 5.2 Inspect an Existing Multi-Arch Image

```bash
docker buildx imagetools inspect alpine:3.20
```

```text
Name:      docker.io/library/alpine:3.20
MediaType: application/vnd.oci.image.index.v1+json
Digest:    sha256:a8560b36...

Manifests:
  Name:        docker.io/library/alpine:3.20@sha256:1111...
  Platform:    linux/amd64

  Name:        docker.io/library/alpine:3.20@sha256:2222...
  Platform:    linux/arm64/v8
  ...
```

`docker manifest inspect alpine:3.20` shows the same raw JSON. `imagetools` is preferred because it works with OCI indexes and needs no experimental flag.

### 5.3 Create a Multi-Platform Builder

```bash
docker buildx create --name multi --driver docker-container --use --bootstrap
docker buildx ls
```

```text
NAME/NODE      DRIVER/ENDPOINT              STATUS   PLATFORMS
multi*         docker-container
 \_ multi0     \_ unix:///var/run/docker.sock running  linux/arm64, linux/amd64, linux/amd64/v2, linux/riscv64, linux/arm/v7, ...
default        docker
```

Docker Desktop ships QEMU/binfmt handlers already. On a plain Linux Engine host, register them once (this is the documented setup image, and it modifies kernel binfmt registrations only):

```bash
docker run --privileged --rm tonistiigi/binfmt --install all
```

> ⚠️ **Warning:** `--privileged` gives the container full host access. Run it only from the official `tonistiigi/binfmt` image, ideally pinned by digest, and only on build hosts.

### 5.4 Build and Push for Two Platforms

```dockerfile
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY . .
RUN CGO_ENABLED=0 go build -o /out/app .

FROM alpine:3.20
COPY --from=build /out/app /usr/local/bin/app
ENTRYPOINT ["app"]
```

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t myorg/app:1.4.2 \
  --push .
```

```text
#12 exporting to image
#12 pushing layers
#12 pushing manifest for docker.io/myorg/app:1.4.2@sha256:AAAA...
```

`--push` is required (or `--output type=registry`): the classic local image store cannot hold an index unless the containerd image store is enabled. Without either, buildx warns that multi-platform output cannot be loaded and keeps the result only in the build cache.

### 5.5 Cross-Compile Instead of Emulate

Use BuildKit's automatic platform ARGs so the compiler runs natively on the builder and only the output targets the other architecture:

```dockerfile
FROM --platform=$BUILDPLATFORM golang:1.23-alpine AS build
ARG TARGETOS TARGETARCH
WORKDIR /src
COPY . .
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH CGO_ENABLED=0 go build -o /out/app .

FROM alpine:3.20
COPY --from=build /out/app /usr/local/bin/app
ENTRYPOINT ["app"]
```

`BUILDPLATFORM` is the builder's platform, `TARGETPLATFORM` the requested one; `TARGETOS`, `TARGETARCH` and `TARGETVARIANT` are the split parts. The final stage still pulls the correct per-architecture `alpine` base automatically. Go, Rust and .NET cross-compile well; C extensions in Python or Node often need real native or emulated builds.

### 5.6 Run or Pull a Specific Platform

```bash
docker run --rm --platform linux/amd64 alpine:3.20 uname -m
docker pull --platform linux/arm64 myorg/app:1.4.2
```

```text
x86_64
```

On an ARM host the first command runs under emulation (Docker Desktop uses Rosetta or QEMU). It works for testing but is slow and occasionally crashes on JIT-heavy software.

### 5.7 Merge Separately Built Images into One Index

Native builds on separate runners can be combined without rebuilding:

```bash
# on the amd64 runner
docker buildx build --platform linux/amd64 -t myorg/app:1.4.2-amd64 --push .
# on the arm64 runner
docker buildx build --platform linux/arm64 -t myorg/app:1.4.2-arm64 --push .
# anywhere, with push rights
docker buildx imagetools create -t myorg/app:1.4.2 \
  myorg/app:1.4.2-amd64 myorg/app:1.4.2-arm64
```

```text
#1 pushing manifest for docker.io/myorg/app:1.4.2@sha256:AAAA...
```

This avoids emulation entirely. The legacy `docker manifest create/push` does the same but is more manual.

### 5.8 Verify Before Release

```bash
docker buildx imagetools inspect myorg/app:1.4.2 --format '{{json .Manifest.Manifests}}' | head -c 400
for p in linux/amd64 linux/arm64; do
  docker run --rm --platform $p myorg/app:1.4.2 --version
done
```

## 6. Production Usage Notes

- **Build natively where possible.** Use cloud ARM runners (GitHub-hosted arm64 runners, Graviton CI agents) and merge with `imagetools create`; QEMU builds of large projects can take 5-20x longer.
- **Always push the tag as an index**, even if only one platform is built today, so adding a platform later does not change how clients pull.
- **Pin base images by digest of the index**, so each platform gets a consistent base. Dependabot/Renovate can bump these.
- **Test every shipped platform.** An arm64 image that was never executed is unverified; run the smoke test per platform in CI ([§83](../Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)).
- **Kubernetes** schedules the right variant automatically on mixed node pools; use `nodeSelector: kubernetes.io/arch` only to restrict, not to select an image.
- **Cache per platform.** Use a registry or `type=gha` cache exporter; cache keys include the platform ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)).
- **Watch storage and rate limits:** an N-platform image stores N sets of layers, and retention policies must treat the index and its child manifests together ([§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- **Explicit platform in Compose:** `platform: linux/amd64` pins a service for a dependency that lacks arm64.

## 7. Security Considerations

- **Scan every platform.** A vulnerability can exist only in one architecture's packages or binaries; scanners (Trivy, Scout) analyze each manifest in the index ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- **Sign the index digest**, which covers all children (cosign, Notary v2); verify the digest at deploy time ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Binfmt installer is privileged.** Restrict who can run it and prefer builder hosts or Docker Desktop's built-in handlers.
- **Emulated builds are not isolated differently,** but QEMU adds a large, complex attack surface; do not build untrusted Dockerfiles on shared hosts.
- **Provenance and SBOM attestations** (`--provenance=mode=max`, `--sbom=true`) attach build metadata per platform; review them for leaked build args or paths before publishing publicly.
- **Mutable tags:** a retag of `:1.4.2` replaces the whole index; use immutable tags and digest pins for production ([§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `exec format error` at container start | Image architecture does not match host and no emulation | Build/push a multi-arch index or run with `--platform` plus binfmt |
| `no matching manifest for linux/arm64/v8 in the manifest list entries` | Tag has no entry for the host platform | `docker buildx imagetools inspect`; rebuild with the missing platform |
| `Multi-platform build is not supported for the docker driver` | Default driver cannot output an index | `docker buildx create --driver docker-container --use` or enable the containerd image store |
| Local `docker images` does not show the multi-arch build | `--load` cannot load multiple platforms (classic store) | Use `--push`, or build one platform with `--load` |
| Build hangs or segfaults on arm64 under QEMU | Emulation limits (JITs, some Go/Rust toolchains, memory) | Use a native ARM builder or cross-compile |
| `WARNING: image platform (linux/amd64) does not match the detected host platform` | Pulled or ran a non-native image | Intended for emulation; otherwise pull the right platform |
| `unknown/unknown` entries in the index | Provenance/SBOM attestations | Normal; disable with `--provenance=false --sbom=false` if a registry rejects them |
| Registry rejects the push of the index | Registry or proxy lacks OCI index support | Upgrade registry or use Docker v2 manifest list format via `--output type=image,oci-mediatypes=false` |
| QEMU not available for a platform | binfmt not registered | Re-run `tonistiigi/binfmt --install all` after reboot |

## 9. Best Practices

- Publish `linux/amd64` and `linux/arm64` by default unless there is a reason not to.
- Prefer native builders or cross-compilation over QEMU; keep emulation as a fallback.
- Use `BUILDPLATFORM` for build stages and the default (target) platform for the final stage.
- Create a dedicated `docker-container` builder and name it in CI.
- Run `imagetools inspect` and a per-platform smoke test as a release gate.
- Use SBOM/provenance attestations and sign the index digest.
- Pin external base images by index digest and update them on a schedule.
- Document which platforms are supported in the image README.

## 10. Common Anti-Patterns / Mistakes

- Building on an Apple Silicon laptop with plain `docker build` and deploying to amd64 servers.
- Pushing separate tags like `:1.4.2-arm64` and `:1.4.2-amd64` without a combining index, forcing consumers to choose.
- Hard-coding `--platform=linux/amd64` in `FROM` for the final stage "to make it work", silently forcing emulation on ARM hosts.
- Downloading architecture-specific binaries in `RUN curl ...` with a fixed arch in the URL instead of using `$TARGETARCH`.
- Never executing the non-native image in CI.
- Using `docker manifest` (experimental legacy) when `buildx imagetools` covers the use case.
- Retaining or deleting only the index in cleanup, orphaning (or losing) child manifests.

## 11. Interview Questions

**🎯 Beginner:** _"What is a manifest list (image index), and how does `docker pull` know which architecture to download?"_
**Model answer:** A manifest list or OCI image index is a JSON document under a tag that lists several platform-specific image manifests, each identified by `os/arch[/variant]` and a digest. When you `docker pull myorg/app:1.4.2`, the registry returns the index, the client compares its own platform (or the `--platform` value) with the entries, and pulls the matching manifest and its layers. Because of this, one tag works on amd64 and arm64 without the user choosing. You can view it with `docker buildx imagetools inspect`.
_What the interviewer is probing for:_ Understanding that the tag points to an index, not to an image, and that selection is done client-side.

**🎯 Intermediate:** _"A developer builds an image on an M-series Mac and pushes it. The production amd64 cluster shows `exec format error`. Explain and fix it."_
**Model answer:** A plain `docker build` on Apple Silicon produces a `linux/arm64` image, and pushing it publishes a tag with only an arm64 manifest. The amd64 node pulls it (or the only entry) and the kernel cannot execute arm64 binaries. Fix by building for the target platform with `docker buildx build --platform linux/amd64,linux/arm64 --push`, using a `docker-container` builder, or by building in CI on amd64. Confirm with `docker buildx imagetools inspect` that both platforms are present, and add a CI check so a single-arch push cannot ship.
_What the interviewer is probing for:_ Recognizing host-architecture defaults and knowing the buildx multi-platform workflow.

**🎯 Senior:** _"Your multi-arch CI build takes 40 minutes because the arm64 half runs under QEMU. How do you make it fast without losing the single tag?"_
**Model answer:** Remove emulation from the hot path in order of preference. First, cross-compile: run build stages on `$BUILDPLATFORM` and pass `$TARGETOS/$TARGETARCH` to the compiler, which works well for Go, Rust and many Java/.NET builds. Second, use native ARM runners: build each platform on its own runner, push per-platform tags (or `push-by-digest`), then run `docker buildx imagetools create -t app:1.4.2 ...` to assemble the index. Third, add platform-aware remote cache (`--cache-to/--cache-from type=registry` or `gha`) so unchanged layers are reused. Keep a per-platform smoke test and only create the final tag when both pass, so the tag never points to a half-validated index.
_What the interviewer is probing for:_ Practical performance tuning, `BUILDPLATFORM`/`TARGETARCH` fluency, and index assembly.

**🎯 Architect:** _"You are moving a 300-service estate from amd64 to a mixed amd64/Graviton fleet. Define the image strategy, controls and rollout."_
**Model answer:** Make multi-arch indexes the platform default: a shared pipeline template builds `linux/amd64` and `linux/arm64` (native runners for both, merged by `imagetools create`), scans and tests each platform, attaches SBOM/provenance, and signs the index digest. Admission policy requires signed digests and rejects tags. Maintain curated multi-arch base images and track services that cannot support arm64 (native dependencies, vendor binaries) with an explicit `nodeSelector` or taint-based pinning until fixed. Roll out by adding Graviton node pools with a small share of replicas, comparing latency, cost and error rate, then shifting traffic gradually; rollback is draining the ARM pool because the same tag works on both. Retention rules treat indexes and children as a unit, and metrics track per-architecture build time and cost.
_What the interviewer is probing for:_ Fleet-level governance, supply chain controls, phased migration and rollback thinking.

## 12. Common Misconceptions

- "A multi-arch image is one fat image containing all binaries." It is an index pointing to separate images; clients download only one.
- "`--load` works for multi-platform builds." Not with the classic image store; push, or use the containerd image store.
- "QEMU makes ARM images identical to native ones." Behavior is the same in principle, but performance and some runtime features differ.
- "Docker Hub tags like `alpine:3.20` are single images." Most official images are indexes.
- "The platform is chosen at build time inside the image." The client chooses at pull time from the index.
- "`docker manifest` is the only way to create an index." `buildx imagetools create` and `buildx build --push` do it too.

## 13. 🔑 Key Takeaways

- Multi-arch = one tag, an OCI image index pointing to per-platform manifests; the client picks.
- Build with `docker buildx build --platform linux/amd64,linux/arm64 --push` on a `docker-container` builder.
- Prefer native builders or `BUILDPLATFORM` cross-compilation over QEMU emulation.
- Merge separately built images with `docker buildx imagetools create`.
- Inspect with `docker buildx imagetools inspect`; test and scan every platform; sign the index digest.
- `exec format error` almost always means an architecture mismatch.

## 14. Related Concepts & What's Next

Related: image manifests and config ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), BuildKit basics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), tagging and push workflows ([§70](Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)), retention ([§71](Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)), supply chain signing ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)), and the pipeline-focused treatment in [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md). Part 10 begins with multi-stage builds, the pattern behind the cross-compilation technique shown here.

**Next Section:** [§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md) — `Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md`
