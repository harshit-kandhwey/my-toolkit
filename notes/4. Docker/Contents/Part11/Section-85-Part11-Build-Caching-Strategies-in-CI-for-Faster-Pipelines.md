# Section 85 (Part 11): Build Caching Strategies in CI for Faster Pipelines

## 1. Definition

**Plain language:** On your laptop, Docker remembers earlier builds, so unchanged steps finish instantly. CI runners are usually brand new for each job and remember nothing, so every build starts cold. CI build caching is the set of techniques that carry that memory between runs: exporting the BuildKit cache to somewhere durable (a registry, the CI vendor's cache service, or a local directory that CI saves) and importing it at the start of the next build.

**Precise definition:** BuildKit can export and import its build cache through *cache backends*, selected with `--cache-to` and `--cache-from` on `docker buildx build`. Backends include `type=registry` (cache stored as an image-like artifact in a registry), `type=gha` (GitHub Actions cache service), `type=local` (a directory), `type=inline` (cache metadata embedded in the pushed image), `type=s3`, `type=azblob`, and `type=gha`'s analogues for other services. Cache scope is controlled by `mode=min` (only layers of the final image) or `mode=max` (all layers, including intermediate multi-stage layers). A second class of cache is *in-Dockerfile*: `RUN --mount=type=cache` mounts a persistent directory for package managers, which is separate from layer caching ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)).

> 💡 **Tip:** The classic `docker build` using the default `docker` driver cannot export to most backends. Use a `docker-container` builder (`docker buildx create --use`) or the `docker/setup-buildx-action` in GitHub Actions.

## 2. Why This Matters

- Cold builds dominate pipeline time: dependency installation and compilation commonly take minutes, while a fully cached build takes seconds.
- Faster feedback means shorter developer loops, fewer context switches and lower CI minutes bills.
- Poorly designed caching produces the opposite problem: slow cache uploads and downloads that cost more than the rebuild, or stale caches that hide broken builds.
- Cache poisoning is a supply-chain risk; shared caches need thought ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- Interviewers ask "why is our CI Docker build slow and how would you speed it up" as a practical platform question.

## 3. Prerequisites and Dependencies

You must understand how layer cache invalidation works ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), BuildKit basics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md), [§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), multi-stage builds ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), and `.dockerignore` and build context ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)). The pipeline context comes from [§80](Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md) and [§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md); multi-platform cache is in [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md).

## 4. Architecture / Conceptual Diagram

```text
 Ephemeral CI runner (empty disk)
┌───────────────────────────────────────────────────────────┐
│ buildx (docker-container driver, BuildKit)                │
│                                                           │
│   --cache-from ───────► import: pull cache manifest,      │
│        ▲                 fetch only layers needed         │
│        │                                                  │
│   build graph: FROM ► COPY deps ► RUN install ► COPY src  │
│        │              HIT         HIT          MISS ► RUN │
│        ▼                                                  │
│   --cache-to ─────────► export: push new/changed layers   │
└────────┬──────────────────────────────▲───────────────────┘
         │ read                         │ write
         ▼                              │
 ┌──────────────────────── Cache backends ───────────────────────┐
 │ registry : app:buildcache   (portable, any CI, needs push)    │
 │ gha      : GitHub cache API (fast, 10 GB repo limit)          │
 │ local    : dir saved by CI cache action (actions/cache, etc.) │
 │ inline   : metadata in the pushed image tag (min mode only)   │
 │ s3/azblob: object storage (self-hosted runners at scale)      │
 └───────────────────────────────────────────────────────────────┘

 mode=min  : cache only layers present in the final image
 mode=max  : also cache intermediate stages (builder stage, test stage)
```

- **Import is lazy:** BuildKit downloads only the cached layers a cache hit actually needs.
- **Key point:** cache hits depend on identical instruction text and identical input checksums, not on file timestamps ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).
- **Two caches:** layer cache (whole `RUN` results) and mount cache (`--mount=type=cache` directories, such as `~/.cache/pip`, which BuildKit keeps on the builder and which do not export with `--cache-to`).

## 5. Hands-On

### 5.1 First, Make the Dockerfile Cache-Friendly

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
COPY . .
CMD ["python", "-m", "app"]
```

Dependency manifests are copied before source so the expensive install layer survives source-only changes. No CI cache backend can fix a Dockerfile that copies `.` first.

### 5.2 Registry Cache (Portable Across Any CI)

```bash
docker buildx create --name ci --driver docker-container --use
docker buildx build \
  --cache-from type=registry,ref=registry.example.com/shop/api:buildcache \
  --cache-to   type=registry,ref=registry.example.com/shop/api:buildcache,mode=max,image-manifest=true,oci-mediatypes=true \
  -t registry.example.com/shop/api:git-1f3a9c2 --push .
```

```text
#8 importing cache manifest from registry.example.com/shop/api:buildcache
#8 DONE 0.6s
#9 [3/5] RUN pip install -r requirements.txt
#9 CACHED
#14 exporting cache to registry
#14 DONE 4.1s
```

Use a dedicated `buildcache` tag (or one per branch) distinct from release tags. `image-manifest=true,oci-mediatypes=true` improves compatibility with registries that reject the default cache manifest media type (ECR, for example).

### 5.3 GitHub Actions Cache Backend

```yaml
- uses: docker/setup-buildx-action@v3
- uses: docker/build-push-action@v6
  with:
    context: .
    push: true
    tags: ghcr.io/shop/api:${{ github.sha }}
    cache-from: type=gha,scope=api
    cache-to: type=gha,scope=api,mode=max
```

`scope` separates caches of different images or branches in the same repo. GitHub limits cache storage per repository (10 GB at the time of writing) and evicts least-recently-used entries, so a very large `mode=max` cache may thrash.

### 5.4 Local Directory Cache with a CI Cache Action

```yaml
- uses: actions/cache@v4
  with:
    path: /tmp/.buildx-cache
    key: buildx-${{ runner.os }}-${{ hashFiles('requirements.txt', 'Dockerfile') }}
    restore-keys: |
      buildx-${{ runner.os }}-
- run: |
    docker buildx build \
      --cache-from type=local,src=/tmp/.buildx-cache \
      --cache-to   type=local,dest=/tmp/.buildx-cache-new,mode=max \
      -t api:ci --load .
- run: rm -rf /tmp/.buildx-cache && mv /tmp/.buildx-cache-new /tmp/.buildx-cache
```

Writing to a *new* directory then swapping avoids the local cache growing without bound, because `type=local` appends but never prunes old blobs. The `rm`/`mv` above operates on throwaway CI runner paths only. GitLab CI and Jenkins use the same pattern with their own `cache:` / `stash` facilities.

### 5.5 Inline Cache (Simplest, Limited)

```bash
docker buildx build \
  --cache-from type=registry,ref=registry.example.com/shop/api:latest \
  --cache-to type=inline \
  -t registry.example.com/shop/api:latest --push .
```

The cache metadata travels inside the image you already push, so there is no extra tag. It only caches the final image's layers (min mode) and cannot capture multi-stage builder layers, which is where most of the compile time lives.

### 5.6 Multi-Stage with `mode=max` and a Separate Test Target

```dockerfile
FROM golang:1.23 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY . .
RUN --mount=type=cache,target=/root/.cache/go-build go build -o /out/app ./cmd/app

FROM build AS test
RUN go test ./...

FROM gcr.io/distroless/static-debian12
COPY --from=build /out/app /app
ENTRYPOINT ["/app"]
```

```bash
docker buildx build --target test --cache-from type=gha --cache-to type=gha,mode=max .
docker buildx build --cache-from type=gha --cache-to type=gha,mode=max -t api --push .
```

With `mode=max`, the `build` stage layers cached by the first command are reused by the second. With `min` the builder stage would be rebuilt every run.

### 5.7 Persisting `--mount=type=cache` Directories

BuildKit mount caches live on the builder, so on ephemeral runners they vanish. Options: use a long-lived self-hosted builder (remote BuildKit via `buildx create --driver remote`), or inject them with the community `buildkit-cache-dance` approach that saves and restores those directories through the CI cache action.

### 5.8 Measuring the Benefit

```bash
time docker buildx build --no-cache -t api:cold .                       # baseline
time docker buildx build --cache-from type=registry,ref=...:buildcache .  # warm
docker buildx du                                                        # builder cache size
docker buildx prune --keep-storage 10GB                                 # trim the builder cache
```

```text
cold: real 3m42s     warm (source-only change): real 0m21s
```

## 6. Production Usage Notes

- **Choose the backend by environment:** `gha` for GitHub-hosted runners, `registry` for portability or multi-CI, object storage or a persistent remote BuildKit for large monorepos on self-hosted runners.
- **Cache scope per branch with fallback to main:** write to `buildcache-<branch>`, read from `buildcache-<branch>` then `buildcache-main`, so feature branches start warm without polluting main.
- **Only write the cache from trusted branches** (main, protected branches). Pull-request builds from forks should read only.
- **Cache transfer cost:** `mode=max` exports and imports more data. Measure; sometimes `min` plus good Dockerfile ordering is faster end-to-end.
- **Registry cache hygiene:** cache tags accumulate blobs; set lifecycle rules and run garbage collection ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)).
- **Self-hosted runners** can keep a warm local BuildKit instance; `docker buildx prune --keep-storage` or `--filter until=168h` bounds disk use ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).
- **Multi-platform builds** keep separate cache entries per platform; export with the same `ref` and let BuildKit store each platform's blobs ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md), [§79](../Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)).
- **Pin base images by digest or update on a schedule.** A moving `FROM python:3.12-slim` invalidates everything when it changes; add a weekly no-cache build to pick up security patches deliberately ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)).
- **Do not mix CI cache sharing with Docker-in-Docker sidecars** that lose state on every job; see [§81](Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md).

## 7. Security Considerations

- **Cache poisoning:** a cache is trusted input. If an untrusted PR can write to a cache that the release build reads, an attacker can plant a malicious layer. Restrict cache writes to protected branches and use separate caches for untrusted builds.
- **Secrets in layers end up in the cache.** Use `RUN --mount=type=secret` and SSH mounts, never `ARG`/`ENV` secrets, otherwise the layer (and its cache blob) leaks credentials ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Registry cache credentials:** the cache push needs registry write access; scope the token to the cache repository where possible.
- **Stale cache hides vulnerabilities:** a cached `apt-get install` layer keeps old package versions indefinitely. Schedule periodic uncached builds and scan the resulting image ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- **Reproducibility trade-off:** caching makes the output depend on earlier builds, so release builds that need strict provenance may run without cache or with a cache restricted to verified digests.
- **Public cache exposure:** a cache stored in a public repository exposes all intermediate layers, including source in builder stages.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| `Cache export is not supported for the docker driver` | Default `docker` driver in use | `docker buildx create --use --driver docker-container` |
| Every build misses the cache | `COPY . .` before dependency install, changing build args, or timestamps in context via generated files | Reorder Dockerfile, add `.dockerignore`, pin args ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)) |
| Cache hits locally but not in CI | Different base image digest, platform, or builder; cache never exported | Pin base, check `--cache-to` ran on success, same `scope`/`ref` |
| Registry rejects cache push (`unsupported media type`, ECR) | Default cache manifest format | Add `image-manifest=true,oci-mediatypes=true` |
| `gha` cache never restored | Different `scope`, cache evicted at 10 GB, or PR from a fork | Align scopes, reduce size, accept read-only for forks |
| Cache step slower than the build | `mode=max` for a small, fast build, or distant registry | Use `min`/inline, or co-locate the cache registry with runners |
| Local cache directory keeps growing | `type=local` never prunes | Write to a new dir and swap (5.4) |
| Mount cache empty on each run | `--mount=type=cache` lives on the ephemeral builder | Persistent remote builder or cache-dance pattern (5.7) |
| `error: failed to solve: failed to compute cache key` | A path in `COPY` excluded by `.dockerignore` | Fix ignore patterns ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)) |

## 9. Best Practices

- Fix Dockerfile ordering and `.dockerignore` first; add a CI backend second.
- Use a `docker-container` builder in CI and enable `mode=max` when multi-stage builds dominate time.
- Scope caches per image and branch, with fallback to the main-branch cache.
- Let only trusted branches write the cache.
- Use `RUN --mount=type=cache` for package manager downloads, plus a strategy to persist them where needed.
- Measure cold versus warm build time and cache transfer time; keep numbers in the pipeline logs.
- Schedule a periodic no-cache build for freshness and security patches.
- Prune builder and registry caches on a schedule.
- Never place secrets in layers that can be cached.

## 10. Common Anti-Patterns / Mistakes

- Reaching for `--cache-from` while the Dockerfile still starts with `COPY . .`.
- Using only `docker pull image:latest` then `--cache-from image:latest` without BuildKit cache metadata (legacy pattern that no longer works reliably under BuildKit; the image must carry inline cache or use a registry cache ref).
- Letting every PR from any contributor write to the shared main cache.
- A single global cache for unrelated images that evict each other.
- Caching without ever invalidating, so CVE-ridden layers are reused for months.
- Treating `type=local` as a managed cache and never pruning it.
- Exporting `mode=max` for a tiny image and paying more in network than in compile time.
- Disabling cache (`--no-cache`) permanently because "it was once stale," instead of fixing the cause.

## 11. Interview Questions

**🎯 Beginner:** _"Why is a Docker build fast on your laptop but slow on every CI run?"_
**Model answer:** Locally, BuildKit keeps the layer cache on disk, so unchanged steps are reused. A CI runner is typically a fresh VM or container with an empty cache, so each run rebuilds every layer. The fix is to export the cache to a durable location with `--cache-to` and import it in the next run with `--cache-from`, and to order the Dockerfile so dependency installation comes before copying frequently changing source.
_What the interviewer is probing for:_ Understanding that cache is local state and ephemeral runners lose it.

**🎯 Intermediate:** _"Compare `type=inline`, `type=registry` and `type=gha` cache backends. When would you pick each?"_
**Model answer:** Inline embeds cache metadata in the image you push; it is simple but caches only the final image layers, so multi-stage builder layers are lost. Registry stores a dedicated cache artifact in a registry; it is portable across CI systems, supports `mode=max` and per-branch refs, but needs registry write access and lifecycle cleanup. GHA uses GitHub's cache service; it is very fast on hosted runners and needs no registry permissions, but has a size cap with eviction and is tied to GitHub. I pick gha on GitHub-hosted runners, registry for multi-CI or self-hosted setups, and inline only for simple single-stage images.
_What the interviewer is probing for:_ Knowing capabilities and limits of each backend, including `min` versus `max`.

**🎯 Senior:** _"Your cached CI builds stay green but production images contain a vulnerable OpenSSL for months. What happened and how do you fix the pipeline?"_
**Model answer:** The `RUN apt-get install` layer and the unpinned base were served from cache, since the instruction text and inputs never changed. Cache correctness is about inputs, not about the outside world's updates. Fix by scheduling a weekly build with `--no-cache` (or `--pull` plus cache bust via an ARG that changes), updating base images through automated PRs with digest pins, scanning every built image regardless of cache hits, and failing promotion when criticals appear. Add alerts on image age.
_What the interviewer is probing for:_ Recognizing that caching trades freshness for speed and that the pipeline needs deliberate invalidation.

**🎯 Architect:** _"Design the build-cache architecture for 200 repositories on a mix of GitHub-hosted and self-hosted runners with a strict supply-chain policy."_
**Model answer:** Provide a standard reusable build workflow with consistent Dockerfile linting and cache flags. Hosted runners use `gha` scoped per repository and image. Self-hosted runners attach to a pool of persistent remote BuildKit daemons (or Kubernetes-hosted BuildKit) so layer and mount caches stay warm without network transfer, with disk quotas and scheduled prunes. A registry cache in the internal registry serves as the shared fallback, written only by protected-branch jobs through a dedicated identity; PR builds are read-only. Release builds are separated: they use a trusted cache or none, produce signed images with SBOM and provenance attestations, and a nightly uncached build plus scan catches stale layers. Metrics (hit rate, cache transfer time, cold versus warm duration) feed a dashboard so the platform team can tune `min` versus `max` per repository.
_What the interviewer is probing for:_ Balancing speed, cost, isolation and provenance at fleet scale.

## 12. Common Misconceptions

- "`--cache-from` alone makes builds fast." It only reads; without a prior `--cache-to` there is nothing to import.
- "The cache stores my final image." It stores build layers and metadata, not necessarily a runnable image.
- "`mode=max` is always better." It costs more transfer and storage.
- "CI cache and `--mount=type=cache` are the same thing." They are different mechanisms.
- "Cached builds are as secure as fresh ones." They can freeze outdated packages and extend the reach of a poisoned layer.
- "The default `docker build` can use any backend." Only the `docker-container` (or remote/Kubernetes) drivers support exporters.

## 13. 🔑 Key Takeaways

- Ephemeral runners start cold; carry the cache with `--cache-to` / `--cache-from`.
- Dockerfile ordering and `.dockerignore` come first; backends amplify good structure.
- Pick `gha`, `registry`, `local`, `inline` or object storage by CI platform; use `mode=max` for multi-stage builds when it measurably helps.
- Mount caches (`--mount=type=cache`) need separate persistence on ephemeral builders.
- Write cache only from trusted branches; never bake secrets into cacheable layers.
- Schedule uncached builds so speed does not freeze vulnerabilities.

## 14. Related Concepts & What's Next

Related: cache invalidation ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), BuildKit features ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)), reproducible builds ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)), pipelines ([§80](Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§82](Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)), GitOps promotion ([§84](Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)). This closes Part 11 on CI/CD; Part 12 turns to operating containers in production, beginning with [§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md) on logging architectures.

**Next Section:** [§86](../Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md) — `Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md`
