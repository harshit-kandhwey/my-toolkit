# Section 78 (Part 10): Reproducible Builds and Build Args Best Practices

## 1. Definition

**Plain language:** A reproducible build is one where building the same source twice gives you the same image, byte for byte, no matter when or where you build it. Build args (`ARG`, `--build-arg`) are the knobs you hand to a build; used well they make builds predictable, used badly they leak secrets or silently change results.

**Precise definition:** An image build is **reproducible** when identical inputs (Dockerfile, build context, base image content, package sources, build args, `SOURCE_DATE_EPOCH`) produce identical layer digests and therefore an identical image manifest digest ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)). Three sources of drift break this:

- **Input drift:** a mutable tag (`python:3.12`), an unpinned `apt-get install`, a floating dependency range, or a `curl | sh` that fetches whatever is current.
- **Metadata drift:** file modification times, the image config `created` timestamp, and tar ordering baked into layers.
- **Environment drift:** build args or env values that differ between machines (`BUILD_DATE`, `GIT_SHA`, hostnames, user names).

`ARG` declares a build-time variable. It exists only during the build (not in the running container, unlike `ENV`), is scoped to the build stage where it is declared, and, if declared before the first `FROM`, is available only to `FROM` lines unless re-declared inside a stage.

> 💡 **Tip:** In practice "reproducible" has two levels. *Rebuildable* (same inputs, functionally the same image) is what most teams need. *Bit-for-bit identical* requires pinned inputs plus normalised timestamps and is worth the effort mainly for signed or regulated artifacts.

## 2. Why This Matters

- "It worked last week" incidents usually trace to a base image tag or package that moved underneath an unchanged Dockerfile.
- Security response needs to answer "which exact base and packages are in production?" A pinned digest and an SBOM answer it; a floating tag cannot.
- Cache behaviour ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)) depends on stable inputs. A `BUILD_DATE` arg declared early invalidates every layer after it on every build.
- Supply-chain controls such as provenance attestations and signatures ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)) are far more meaningful when a third party can rebuild and compare digests.
- Build args are a classic secret-leak path: values are recorded in image history and attestations.

## 3. Prerequisites and Dependencies

Requires Dockerfile instructions, especially `ARG`, `ENV` and `FROM` ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md), [§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), the layer and manifest model ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), tagging versus digests ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), and BuildKit basics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md), [§75](Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)). Secrets belong in build secret mounts, not args ([§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)). Multi-stage structure ([§73](Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)) determines `ARG` scope.

## 4. Architecture / Conceptual Diagram

```text
  Sources of non-determinism                    Controls
  ─────────────────────────                    ────────
  FROM python:3.12          (mutable tag) ───► FROM python:3.12.7-slim@sha256:...
  apt-get install curl      (latest)      ───► curl=7.88.1-10+deb12u8 or snapshot repo
  pip install flask         (range)       ───► requirements.txt with hashes / lockfile
  file mtimes, created time (wall clock)  ───► SOURCE_DATE_EPOCH + rewrite-timestamp
  ARG BUILD_DATE=$(date)    (changes/build)───► pass as label at the LAST layer, or omit

  ARG scope across stages
  ┌──────────────────────────────────────────────────────────────┐
  │ ARG GO_VERSION=1.23            ◄── global: usable in FROM only│
  │ FROM golang:${GO_VERSION} AS build                            │
  │   ARG GO_VERSION               ◄── re-declare to use in stage │
  │   ARG VERSION                  ◄── stage-local                │
  │   RUN go build -ldflags "-X main.version=${VERSION}" ...      │
  │ FROM gcr.io/distroless/static                                 │
  │   # VERSION is NOT visible here unless declared again         │
  └──────────────────────────────────────────────────────────────┘

  Verification loop
  build #1 ──► digest A ┐
  build #2 ──► digest B ┴─► A == B ?  yes: reproducible   no: diff layers
                                      (diffoci / skopeo / docker inspect)
```

- **Cache key effect:** a `--build-arg` value participates in the cache key of the first instruction that *uses* it, and everything below that point rebuilds when it changes.
- **Visibility:** args used in `RUN` appear in `docker history` and in provenance attestations. Predefined proxy args (`HTTP_PROXY` and similar) are an exception: they are excluded from history by default.

## 5. Hands-On

### 5.1 Pin the Base Image by Digest (Keep the Tag for Humans)

```bash
docker buildx imagetools inspect python:3.12.7-slim-bookworm --format '{{json .Manifest.Digest}}'
```

```text
"sha256:3f1d...e9a2"
```

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12.7-slim-bookworm@sha256:3f1d...e9a2
```

When both are present the digest wins and the tag is documentation. A digest of a multi-platform index pins all platforms at once ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)). Let a bot (Renovate or Dependabot) bump tag and digest together through reviewed pull requests, so you pin without going stale.

### 5.2 Pin OS Packages and Avoid Cache Surprises

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl=7.88.1-10+deb12u8 \
        ca-certificates=20230311 \
    && rm -rf /var/lib/apt/lists/*
```

Exact versions disappear from Debian mirrors once superseded, so this breaks loudly rather than drifting. For true repeatability point apt at a snapshot service (for example `snapshot.debian.org` with a fixed timestamp) or an internal mirror you control. Alpine users pin with `apk add curl=8.9.1-r2` and a fixed Alpine minor release.

### 5.3 Lock Language Dependencies

```dockerfile
# Python: hashes make tampering and drift fail the build
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Node: npm ci refuses to run if package-lock.json disagrees with package.json
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Go: modules are content-addressed via go.sum
COPY go.mod go.sum ./
RUN go mod download && go mod verify
```

Never use `npm install`, unpinned `pip install`, or `go get @latest` inside a Dockerfile.

### 5.4 Normalise Timestamps with SOURCE_DATE_EPOCH

```bash
export SOURCE_DATE_EPOCH=$(git log -1 --pretty=%ct)

docker buildx build \
  --build-arg SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH \
  --output type=image,name=registry.example.com/app:1.4.2,push=false,rewrite-timestamp=true \
  --provenance=false .
```

BuildKit (0.13 and later) clamps file mtimes in the produced layers to the epoch and sets the image config `created` field to it when `rewrite-timestamp=true`. Build tools inside the Dockerfile that honour `SOURCE_DATE_EPOCH` (GNU tar, Python wheels, Go with `-trimpath`) pick up the same value because it is passed as a build arg. Using the commit time ties the timestamp to the source rather than to the build clock.

### 5.5 Prove It: Build Twice and Compare

```bash
for i in 1 2; do
  docker buildx build --no-cache \
    --build-arg SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH \
    --output type=oci,dest=out$i.tar,rewrite-timestamp=true \
    --provenance=false --sbom=false .
done
sha256sum out1.tar out2.tar
```

```text
9c41...a7d0  out1.tar
9c41...a7d0  out2.tar
```

Identical hashes mean identical layers and manifests. If they differ, extract both OCI layouts and compare layer by layer (`diffoci diff` from the containerd ecosystem, or `tar -tvf` on each layer blob). Attestations carry build timestamps and builder identity, so disable them for this comparison and attach them to the published image afterwards.

### 5.6 Build Args: Declare, Default, Scope

```dockerfile
# syntax=docker/dockerfile:1
ARG NODE_VERSION=22.9.0
ARG DEBIAN_RELEASE=bookworm

FROM node:${NODE_VERSION}-${DEBIAN_RELEASE}-slim AS build
ARG NODE_ENV=production            # re-declared: stage scope
WORKDIR /src
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:${NODE_VERSION}-${DEBIAN_RELEASE}-slim
ARG APP_VERSION=dev
LABEL org.opencontainers.image.version=${APP_VERSION}   # placed late: cheap to change
COPY --from=build /src/dist /app
USER node
CMD ["node", "/app/server.js"]
```

```bash
docker buildx build --build-arg APP_VERSION=1.4.2 --build-arg NODE_VERSION=22.9.0 -t app:1.4.2 .
```

Putting `ARG APP_VERSION` and its use at the end means a version bump rebuilds only the label layer, and the expensive `npm ci` layer stays cached ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)).

### 5.7 Forcing Required Args and Seeing What Leaked

```dockerfile
ARG TARGET_ENV
RUN test -n "$TARGET_ENV" || (echo "TARGET_ENV is required" >&2; exit 1)
```

```bash
docker buildx build --check .                       # lints, including secret-looking ARG names
docker history --no-trunc app:1.4.2 | grep -i version
```

```text
Warning: SecretsUsedInArgOrEnv: Do not use ARG or ENV instructions for sensitive data (ARG "API_TOKEN")
<missing>  ...  |1 APP_VERSION=1.4.2 /bin/sh -c npm run build
```

`docker buildx build --check` (BuildKit build checks, Dockerfile frontend 1.8 and later) flags suspicious names and also warns on undefined or unused args. The history line proves arg values are readable by anyone who can pull the image.

### 5.8 Compose and CI Wiring

```yaml
services:
  api:
    build:
      context: .
      args:
        APP_VERSION: ${APP_VERSION:-dev}
        SOURCE_DATE_EPOCH: ${SOURCE_DATE_EPOCH:?set from git}
```

A `build.args` entry with no value (`- NPM_TOKEN`) passes the host environment variable through, which is exactly the leak to avoid; give every arg an explicit, non-secret value or a default.

## 6. Production Usage Notes

- **Single source of truth for versions:** keep tool and base versions in one place (a `versions.env`, Renovate-managed `ARG` defaults, or a bake file) so CI and developers build the same thing.
- **docker-bake.hcl** captures args, tags, platforms and attestations in a file; it is the clean way to express "the official build" and reuse it locally and in CI ([§79](Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)).
- **Tag plus digest in deployments:** record the digest that was actually built and deploy by digest. Tags stay as human labels ([§70](../Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)).
- **Generate provenance and SBOM** (`--provenance=mode=max --sbom=true`) on release builds. They are the audit record of which args and base digest were used.
- **Expect the containerd image store differences:** with the containerd-backed image store (default on recent Docker Desktop and newer fresh Engine installs, opt-in on Engine 27/28) local digests can differ from classic store behaviour; compare digests from the registry or OCI export, not from `docker images` alone.
- **Dockerfile frontend pinning:** `# syntax=docker/dockerfile:1` floats within v1 for features; pin to a full version or digest if even frontend changes must not affect output.

## 7. Security Considerations

- **Never pass secrets as build args or `ENV`.** Values appear in `docker history`, in the image config for `ENV`, and in SLSA provenance at `mode=max`. Use `RUN --mount=type=secret` ([§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)).
- **Digest pinning defends against tag hijack** and registry-side retagging, but it also freezes known vulnerabilities in place. Pair it with scheduled automated bumps and scanning ([§63](../Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)).
- **Hash-checked downloads:** for binaries fetched in the Dockerfile, verify a checksum (`echo "<sha256>  file" | sha256sum -c -`) or use `ADD --checksum=sha256:...` rather than trusting TLS alone.
- **Never `curl | sh`** installers: the content is unpinned and unauditable.
- **Build args can change behaviour:** an arg that selects a base image, mirror URL or package index lets whoever controls CI variables redirect the supply chain. Restrict who can set them and avoid args that accept arbitrary URLs.
- **Provenance and signatures** (cosign, Docker Content Trust) prove who built an image, not that it is reproducible; reproducibility lets a second party verify it independently.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Digest differs between two identical builds | Timestamps, tar order, or a floating input | Set `SOURCE_DATE_EPOCH` with `rewrite-timestamp=true`; diff layers to find the moving file |
| Every build re-runs `npm ci` | `ARG BUILD_DATE`/`GIT_SHA` declared before the install step | Move volatile args below expensive layers or into labels at the end |
| `ARG` value empty inside stage | Declared before `FROM` but not re-declared in the stage | Add `ARG NAME` inside the stage |
| `ARG` value not available in second stage | Args are per stage | Re-declare or pass via `COPY --from` of an output file |
| `E: Version '1.2.3-4' for 'pkg' was not found` | Pinned apt version rotated out of the mirror | Use snapshot repo or bump pin through a bot |
| Warning: `SecretsUsedInArgOrEnv` | Sensitive-sounding arg name | Switch to a secret mount, rename only if truly non-secret |
| `One or more build-args were not consumed` | Arg passed but never declared with `ARG` | Declare it or remove the flag; the warning catches typos |
| Pull of pinned digest fails with `manifest unknown` | Digest was of one platform or the image was garbage-collected | Pin the index digest; check retention ([§71](../Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)) |
| Local and CI digests differ | Different image store, BuildKit version or frontend | Compare registry digests; pin builder and frontend versions |

## 9. Best Practices

- Pin `FROM` to tag and digest, and automate updates.
- Use lockfiles and install commands that fail on mismatch (`npm ci`, `--require-hashes`, `go mod verify`).
- Pin or snapshot OS package sources; avoid `latest` anywhere in a build.
- Set `SOURCE_DATE_EPOCH` from the commit time and use `rewrite-timestamp=true` for release builds.
- Declare every arg explicitly, give non-secret defaults, and place volatile args as late as possible.
- Use global `ARG` for versions used in `FROM`, and re-declare inside stages that need them.
- Run `docker buildx build --check` in CI and treat warnings as failures.
- Verify reproducibility by building twice in CI for release branches and comparing digests.
- Record provenance and an SBOM for every release image.

## 10. Common Anti-Patterns / Mistakes

- `FROM ubuntu:latest` or `FROM node` with no version.
- `ARG BUILD_DATE=$(date)` style stamping near the top of the Dockerfile, destroying the cache.
- Passing `--build-arg GITHUB_TOKEN=...` to clone private repos.
- Treating `ARG` as a runtime setting; it is gone once the build ends (use `ENV` for runtime, and see [§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)).
- Pinning a digest once and never updating it, leaving a frozen vulnerable base.
- Using `ENV` copies of args (`ENV VERSION=$VERSION`) without realising they persist in the image and in every container.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `ARG` and `ENV`, and can a running container read a `--build-arg` value?"_
**Model answer:** `ARG` is available only during the build, scoped to the stage where it is declared, and is set with `--build-arg` or a default. `ENV` is stored in the image config and exists in every container started from it. A running container cannot read an `ARG` unless the Dockerfile copies it into `ENV` or a file. However, `ARG` values used in `RUN` are visible in `docker history`, so neither is a safe place for secrets. An `ARG` declared before the first `FROM` is usable only in `FROM` lines unless re-declared inside a stage.
_What the interviewer is probing for:_ Scope and lifetime of `ARG` versus `ENV`, and awareness of the history leak.

**🎯 Intermediate:** _"Your Dockerfile uses `FROM python:3.12` and `pip install flask`. Production behaves differently from last month with no code change. Explain and fix."_
**Model answer:** Both inputs float. `python:3.12` is a mutable tag that moves with patch releases and rebuilt OS layers, and unpinned `pip install` picks up whatever Flask and its transitive dependencies are current. Fix by pinning the base to a specific version tag plus digest, committing a lockfile with hashes (`pip install --require-hashes -r requirements.txt`), and pinning or snapshotting OS packages. Add Renovate or Dependabot so updates arrive as reviewed pull requests. Deploy by digest and keep the SBOM so you can diff what changed between releases.
_What the interviewer is probing for:_ Identifying input drift and a practical pin-and-update workflow rather than "pin once".

**🎯 Senior:** _"Security wants to rebuild a release independently and get the identical image digest. What blocks that, and what do you change?"_
**Model answer:** Beyond input pinning, layers embed file mtimes and the config embeds a creation time, so two builds differ even with identical content. Set `SOURCE_DATE_EPOCH` to the commit timestamp, pass it as a build arg for tools that honour it, and export with `rewrite-timestamp=true` on BuildKit 0.13 or later. Remove nondeterministic steps (`apt-get upgrade`, downloads without checksums, build-time stamps), build with `--no-cache` and with attestations off for comparison, and compare the OCI archive hashes. When digests differ, extract layers and diff to find the offending file. Publish provenance separately, since attestations contain timestamps and builder identity by design.
_What the interviewer is probing for:_ Knowledge of metadata drift, BuildKit's timestamp rewriting, and a verification method.

**🎯 Architect:** _"Design the build-arg and versioning policy for 200 services built in a shared CI platform."_
**Model answer:** Central base images are published by a platform pipeline with pinned digests and a defined refresh cadence; service Dockerfiles reference them by digest through a bot-managed version file. Standardise a short allow-list of args (`APP_VERSION`, `SOURCE_DATE_EPOCH`, tool versions), enforced by `buildx build --check` and a Dockerfile linter in CI, with a hard ban on secret-named args and a secret-mount path for credentials. Builds run through bake files so flags are identical locally and in CI, produce provenance and SBOMs, and record the output digest in the deployment manifest. Release branches run a double-build digest comparison as a canary for lost reproducibility. Exceptions (non-deterministic toolchains) are documented rather than silently tolerated, and base image refresh is automated so pinning never turns into stale, vulnerable images.
_What the interviewer is probing for:_ Governance at scale: pin-and-refresh balance, policy enforcement, auditability.

## 12. Common Misconceptions

- "Pinning the tag is enough." Tags are mutable; only a digest is immutable.
- "Reproducible means no updates." It means updates are deliberate and recorded.
- "`ARG` values are hidden because they are build-time." They are visible in history and attestations.
- "`--no-cache` makes a build reproducible." It removes cache effects but not drifting inputs or timestamps.
- "Build args are inherited by later stages." Each stage must declare what it uses.

## 13. 🔑 Key Takeaways

- Reproducibility needs pinned inputs plus normalised metadata (`SOURCE_DATE_EPOCH`, `rewrite-timestamp`).
- Pin base images by digest and automate the bumps.
- Lock and hash-check every dependency layer; no `latest`, no `curl | sh`.
- `ARG` is build-time, per stage, and visible in history: never put secrets there.
- Put volatile args late to protect the cache; use `--check` to catch mistakes.
- Verify by building twice and comparing digests, and record provenance and SBOM.

## 14. Related Concepts & What's Next

Related: layer model ([§16](../Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)), `ARG` and `ENV` ([§19](../Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)), tagging ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)), cache invalidation ([§74](Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), build secrets ([§76](Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)), SBOM and signing ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)). Next, [§79](Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md) takes these controls into `docker buildx` and multi-platform pipelines, where bake files and platform-specific args matter.

**Next Section:** [§79](Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md) — `Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md`
