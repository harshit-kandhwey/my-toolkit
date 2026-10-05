# Section 74 (Part 10): Layer Caching Strategies and Build Cache Invalidation

## 1. Definition

**Plain language:** Every Dockerfile instruction produces a build step. If Docker can prove that a step would produce exactly what it produced last time, it reuses the stored result instead of running the step again. That reuse is the **build cache**. A *cache invalidation* is the moment Docker decides it cannot prove that, so it re-runs the step and every step after it.

**Precise definition:** BuildKit keys each build step (an LLB vertex) by a content-based checksum made from the step's definition (the instruction and its resolved arguments), its parent step's cache key, and any inputs it consumes. For `COPY` and `ADD` the inputs are the **content checksum of the copied files** (file contents, mode, and ownership; not modification time). For `RUN` the key is the **command string** plus the parent chain, not the command's output, so `RUN apt-get update` is a cache hit forever until something above it changes. Because each key includes the parent's key, a miss at step N invalidates all steps after N in that stage. Cache can be stored in the local builder, exported to a registry or other backends (`--cache-to`), and imported (`--cache-from`). Separately from layer caching, `RUN --mount=type=cache` gives a step a persistent directory (for package-manager downloads) that survives across builds even when the step itself is re-executed ([§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)).

> 💡 **Tip:** Order instructions from least-frequently-changing to most-frequently-changing. Dependencies change rarely; source code changes on every commit.

## 2. Why This Matters

- A well-ordered Dockerfile turns a 6-minute rebuild into a 5-second one when only application code changed.
- Cache behavior drives CI cost and developer feedback loops ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)).
- Over-aggressive caching is a correctness and security problem: stale `apt-get update` layers freeze vulnerable package versions into your image.
- "Why did it rebuild everything?" and "why did it NOT pick up my change?" are the two most common build questions, and both are cache-key questions.
- Frequently appears in interviews because it separates people who write Dockerfiles from people who understand them.

## 3. Prerequisites and Dependencies

You need image layer fundamentals ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), Dockerfile instructions ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)), `ARG`/`ENV` behavior ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), build context and `.dockerignore` ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), and the build command ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)). Multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)) determine which stages are even executed, which interacts with caching. The layered storage that holds results is explained in [§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md).

## 4. Architecture / Conceptual Diagram

```text
  Dockerfile (stage "build")                    Cache decision per step
  ┌──────────────────────────────┐
  │ 1 FROM node:22-slim          │──► key = digest of base image reference  ──► HIT
  │ 2 WORKDIR /app               │──► key = f(key1, "WORKDIR /app")          ──► HIT
  │ 3 COPY package*.json ./      │──► key = f(key2, checksum of the 2 files) ──► HIT
  │ 4 RUN npm ci                 │──► key = f(key3, "npm ci")                ──► HIT (slow step skipped)
  │ 5 COPY . .                   │──► key = f(key4, checksum of all files)   ──► MISS (src changed)
  │ 6 RUN npm run build          │──► key = f(key5, "npm run build")         ──► MISS (parent missed)
  └──────────────────────────────┘
                                   Once one step misses, everything below it re-runs.

  Where cache lives and flows
  ┌───────────────┐   --cache-from    ┌───────────────────┐
  │ Remote cache  │ ────────────────► │  BuildKit builder │ ──► local layer/cache store
  │ (registry,    │ ◄──────────────── │                   │
  │  gha, s3 ...) │   --cache-to      └─────────┬─────────┘
  └───────────────┘                             │ RUN --mount=type=cache
                                                ▼
                                   persistent dir (e.g. /root/.npm)
                                   survives even when the RUN step re-executes
```

- **Cache key chain:** each step's key embeds its parent's key, so invalidation cascades downward.
- **COPY/ADD** compare file content checksums; touching a file without changing it does not invalidate.
- **RUN** compares only the command text; the outside world (package repos, `git clone` targets) is invisible to the cache.
- **Build args and env:** an `ARG` or `ENV` value used by a step is part of the key; changing it invalidates that step and below.

## 5. Hands-On

### 5.1 The Naive Dockerfile (Cache Busts on Every Edit)

```dockerfile
# Dockerfile.naive
FROM node:22-slim
WORKDIR /app
COPY . .
RUN npm ci
RUN npm run build
```

Any source edit changes the checksum of `COPY . .`, so `npm ci` re-downloads all dependencies every time.

### 5.2 The Ordered Dockerfile (Dependencies First)

```dockerfile
# Dockerfile
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build
```

```bash
docker build --progress=plain -t web:dev .
# edit src/index.js, then rebuild
docker build --progress=plain -t web:dev .
```

```text
#7 [3/6] COPY package.json package-lock.json ./
#7 CACHED
#8 [4/6] RUN npm ci
#8 CACHED
#9 [5/6] COPY . .
#10 [6/6] RUN npm run build
```

`CACHED` marks reused steps. Only the source copy and the build re-run.

### 5.3 Cache Mounts: Fast Even When the Step Re-Runs

```dockerfile
# syntax=docker/dockerfile:1
FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY . .
RUN npm run build
```

When `package-lock.json` changes, `npm ci` re-executes, but tarballs in `/root/.npm` are reused, so only new packages download. The mount contents are **not** part of the image.

Equivalents for other ecosystems:

```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build go build ./...
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends curl
```

For Debian images, remove `/etc/apt/apt.conf.d/docker-clean` first, otherwise apt deletes its cache after each install.

### 5.4 Bind Mounts: Use Files Without a COPY Layer

```dockerfile
RUN --mount=type=bind,source=package.json,target=package.json \
    --mount=type=bind,source=package-lock.json,target=package-lock.json \
    --mount=type=cache,target=/root/.npm \
    npm ci
```

The files are visible only during that `RUN`, they are checksummed into the cache key, and they add no layer.

### 5.5 Controlling Staleness: update + install Together, and Cache Busting

```dockerfile
# GOOD: one RUN, so update can never be cached apart from install
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
```

To deliberately refresh a cached `RUN` (for example to pick up security updates), pass a changing build arg that the step consumes:

```dockerfile
ARG CACHE_BUST=0
RUN echo "$CACHE_BUST" && apt-get update && apt-get upgrade -y
```

```bash
docker build --build-arg CACHE_BUST=$(date +%Y%m%d) -t web:dev .   # refresh daily
docker build --no-cache -t web:dev .                                # ignore all cache
docker build --no-cache-filter build -t web:dev .                   # ignore cache for stage "build" only
docker build --pull -t web:dev .                                    # re-check the base image tag first
```

`--pull` matters: without it a locally present `node:22-slim` is reused even if the registry tag has moved.

### 5.6 Remote Cache Import and Export

```bash
docker buildx create --use --driver docker-container --name ci-builder   # needed for non-default cache backends

docker buildx build \
  --cache-from type=registry,ref=registry.example.com/web:buildcache \
  --cache-to   type=registry,ref=registry.example.com/web:buildcache,mode=max,image-manifest=true \
  -t registry.example.com/web:1.4.2 --push .
```

- `mode=min` (default) exports only layers of the final image; `mode=max` also exports intermediate stages, which is what makes multi-stage builds cache well.
- Other backends: `type=gha` (GitHub Actions cache), `type=s3`, `type=azblob`, `type=local,dest=./cache`, `type=inline` (embeds cache metadata in the pushed image; min mode only).

### 5.7 Inspecting Cache and Disk Use

```bash
docker buildx du                    # cache records, sizes, last used
docker buildx du --verbose
docker builder prune --filter until=168h        # drop cache unused for a week
docker builder prune --keep-storage 10GB        # cap cache size
```

## 6. Production Usage Notes

- **Layer ordering template:** base image, OS packages, language toolchain config, dependency manifests, dependency install, source copy, build, runtime config (`ENV`, `EXPOSE`, `USER`, `CMD`).
- **CI runners are ephemeral:** the local cache is empty on each job, so you must import and export cache (registry, `gha`, S3) or builds are always cold ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)).
- **Cache mounts are local to a builder.** They do not travel through `--cache-to`; in CI you must persist the mount directory by other means (for example the `buildkit-cache-dance` approach for GitHub Actions) or accept cold package caches.
- **Pin base images by digest** (or refresh deliberately) so cache hits reflect a known base ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md), [§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)).
- **Scheduled rebuilds with `--no-cache` or `--pull`** (weekly or nightly) pick up OS security patches that a perpetually warm cache would hide.
- **Mind the monorepo:** copy only the manifests and sources a service needs, or one unrelated edit invalidates every service image. Use `.dockerignore` to exclude `.git`, `node_modules`, build output and logs.
- **Disk growth:** unattended build hosts accumulate cache; schedule `docker builder prune` ([§33](../Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)).

## 7. Security Considerations

- **Frozen vulnerabilities:** a cached `apt-get update && install` layer keeps old package versions indefinitely. Rebuild with `--no-cache`/`--pull` on a schedule and scan outputs ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- **Secrets in cached layers:** a secret written by a `RUN` or copied with `COPY` is baked into a layer that is then cached, exported with `--cache-to` and shared. Use secret mounts instead ([§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Cache poisoning:** a shared remote cache is a trust boundary. If untrusted pull requests can write to it, they can plant layers that later trusted builds reuse. Give PR builds read-only cache access and let only main-branch builds export.
- **Build args are visible:** `ARG` values appear in `docker history` and the image's build metadata; never use them for secrets, and do not put credentials in a cache-busting arg.
- **Registry cache refs** need the same access control as images; cache manifests can reveal the contents of intermediate stages.
- **Pin and verify:** digest-pinned bases make a cache hit equal a known input, which supports provenance claims ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Every build re-runs `npm ci` / `pip install` | `COPY . .` precedes the install, or the manifest changes each build | Copy manifests first; check `.dockerignore` so build output or logs are not in context |
| Cache never hits in CI | Fresh runner, no `--cache-from`, or default `docker` driver without cache export | Use a `docker-container` builder plus registry/`gha` cache |
| Change not reflected in image | Cached `RUN git clone` / `curl` step; remote content changed but the command text did not | Add a version `ARG`, pin a commit or checksum, or use `--no-cache-filter` |
| Whole build invalid after a tiny edit | A cheap step placed early (for example `COPY . .` or an `ARG` with changing value) | Move volatile steps late; declare `ARG`s just before first use |
| `CACHED` missing after `git checkout` | Not caused by mtime (BuildKit uses content), so check for changed line endings, file mode or generated files in context | Normalize EOL with `.gitattributes`; ignore generated files |
| Out-of-date OS packages | Perpetual cache hit on `apt-get update` | Scheduled `--no-cache` build, or cache-bust arg |
| `no space left on device` on build host | Unbounded build cache | `docker builder prune`, `--keep-storage` |
| Cache mount appears empty in CI | Mounts are builder-local and not exported | Persist mount dir by CI-specific mechanism, or rely on layer cache |
| `--cache-to` error: cache export not supported | Using the default `docker` driver | `docker buildx create --driver docker-container --use` |

Debugging recipe: `docker build --progress=plain .`, find the first step without `CACHED`, then ask what in its key changed (file content, arg, parent, base image digest).

## 9. Best Practices

- Order instructions by change frequency; put dependency manifests before source.
- Combine `apt-get update` with `install` in one `RUN` and clean lists in the same layer (or use cache mounts).
- Use `RUN --mount=type=cache` for package-manager downloads; use `--mount=type=bind` for manifests when a `COPY` layer is not needed.
- Keep `.dockerignore` tight so the context checksum only changes when relevant files change ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)).
- Declare `ARG` as late as possible, since an `ARG` that changes invalidates every step that follows its first use.
- Use stages so the expensive toolchain layers stay cached independently of the final runtime stage ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)).
- Export cache from trusted branches only; import it everywhere.
- Rebuild without cache on a schedule to absorb base image and OS patches.
- Pin base images by digest and update them through an automated PR (Renovate or Dependabot).

## 10. Common Anti-Patterns / Mistakes

- `COPY . .` as the first step after `FROM`.
- Separate `RUN apt-get update` and `RUN apt-get install` lines (stale index, broken installs).
- Using `--no-cache` on every build "to be safe", which discards the benefit and slows CI.
- Cache-busting with `ADD <url>` or a timestamp `ARG` placed near the top, invalidating everything.
- Running `RUN git clone ...` of a moving branch and trusting the cache to refresh it.
- Assuming a cache mount is part of the image or is available at run time.
- Letting forks or unreviewed PRs write to the shared remote cache.

## 11. Interview Questions

**🎯 Beginner:** _"Why do experienced Dockerfiles copy `package.json` and run `npm install` before copying the rest of the source?"_
**Model answer:** Each instruction creates a cached step keyed by its parent and its inputs. If I copy all source first, any code edit changes that step's checksum and every later step re-runs, including the slow dependency install. By copying only the manifest and lock file first and installing, the install step's inputs change only when dependencies change, so it stays cached across ordinary code edits. Then `COPY . .` and the build re-run quickly. The general rule is to order instructions from least to most frequently changing.
_What the interviewer is probing for:_ Understanding that invalidation cascades downward and that ordering is the main lever.

**🎯 Intermediate:** _"Your image was built last month and a CVE fix was released for a package installed by `RUN apt-get update && apt-get install -y libfoo`. Rebuilding keeps producing the old version. Why, and what are your options?"_
**Model answer:** BuildKit keys a `RUN` by its command text and parent chain, not by what the command would download today. Nothing in the key changed, so it is a cache hit and the old layer is reused. Options: rebuild with `--no-cache`, or `--no-cache-filter` for just that stage; use `--pull` so the base image refreshes (a new base digest invalidates everything downstream); or add a cache-bust `ARG` bumped on a schedule. For fleet hygiene I would run scheduled no-cache rebuilds in CI, pin base images by digest with automated update PRs, and scan the result so the fix is verified rather than assumed.
_What the interviewer is probing for:_ Knowing that RUN is not content-addressed and that caching trades freshness for speed.

**🎯 Senior:** _"CI builds take 12 minutes because runners are ephemeral. Design the caching strategy for a multi-stage Java/Node image, and explain what `--cache-to` does and does not carry."_
**Model answer:** Use a `docker-container` buildx builder and import and export cache to a registry (or `type=gha`) with `mode=max`, so intermediate stages such as the dependency-resolution and compile stages are cached, not only the final image layers. Structure the Dockerfile so dependency manifests come first, and add `RUN --mount=type=cache` for Maven/npm caches. Be explicit that cache mounts are builder-local and are not exported by `--cache-to`, so in CI I either persist that directory with a CI cache action or accept that dependency downloads repeat when the lockfile changes while layer cache still covers the unchanged case. Only main-branch jobs export; pull request jobs import read-only to prevent poisoning. Track hit rate with `--progress=plain` output and measure before and after.
_What the interviewer is probing for:_ Practical CI cache architecture, `mode=min` vs `max`, and the layer-cache vs cache-mount distinction.

**🎯 Architect:** _"You own build infrastructure for 300 services. Cache hit rates are poor, builds are slow, and security wants fresh patches. Propose a platform-level approach."_
**Model answer:** Provide golden base images, rebuilt and scanned nightly and published by digest, so service builds hit warm cache on a stable parent while still inheriting patches through automated digest-bump PRs (the bump invalidates exactly once per service). Offer a templated Dockerfile and shared build workflow that enforce dependency-first ordering, `.dockerignore`, cache mounts, and consistent cache refs (`registry/cache/<service>`). Run a pool of persistent BuildKit builders or a remote build service with large local cache and GC policy, instead of cold runners, and use read-only cache for untrusted branches. Add a freshness policy: weekly no-cache rebuild for every service and a scanner gate, so caching never silently freezes vulnerable layers. Measure cache hit rate, build duration and cache storage cost per service and review outliers.
_What the interviewer is probing for:_ Balancing speed, freshness and trust at scale, with golden bases and measurable policies.

## 12. Common Misconceptions

- "`RUN` is cached by its output." It is cached by its command and parent, so external changes are invisible.
- "`--no-cache` is the safe default." It is correct but costly; a scheduled strategy is better.
- "Cache mounts end up in the image." They do not; the data exists only for that step.
- "`--cache-to` exports cache mounts." It exports layer cache only.
- "Only the changed step re-runs." Every step after a miss in that stage re-runs.

## 13. 🔑 Key Takeaways

- Cache key = instruction + parent key + input content; a miss cascades to all later steps.
- Order from stable to volatile: manifests, dependency install, then source.
- `RUN` caching is blind to the outside world; schedule `--no-cache`/`--pull` rebuilds for freshness.
- `RUN --mount=type=cache` speeds re-executed steps; it is builder-local and never in the image.
- In CI, import and export cache (`--cache-from`/`--cache-to`, `mode=max` for multi-stage) from trusted jobs only.
- Never put secrets in cached layers or build args; use secret mounts.
- Diagnose with `--progress=plain`: find the first step lacking `CACHED`.

## 14. Related Concepts & What's Next

Related: multi-stage builds ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)), build context mechanics ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), BuildKit basics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), CI cache strategies ([§85](../Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)), reproducible builds ([§78](Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)). Next, [§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md) opens up BuildKit itself: the LLB graph, frontends, mounts, heredocs and exporters that make these cache behaviors possible.

**Next Section:** [§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md) — `Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md`
