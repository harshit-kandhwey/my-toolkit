# Section 94 (Part 13): Dockerfile Best Practices Checklist

## 1. Definition

**Plain language:** A Dockerfile checklist is the short list of rules that make an image small, fast to build, reproducible, secure and well-behaved at run time. This section gathers rules taught across Parts 3, 8 and 10 into one reviewable list.

**Precise definition:** A "good" Dockerfile satisfies six properties: **correct** (right process model: exec form, PID 1, signals), **minimal** (small base, no build tools in the final stage), **cacheable** (instruction order matches change frequency), **reproducible** (pinned base and dependencies, no hidden network state), **secure** (non-root, no baked secrets, least privilege) and **operable** (labels, health check, sensible defaults, documented ports). Each rule below names the property it protects.

> 💡 **Tip:** Turn the checklist into automation. `hadolint` lints the Dockerfile, `docker build --check` (BuildKit build checks) flags rule violations, and `docker scout`/`trivy` check the result.

## 2. Why This Matters

- Image size, build time and attack surface are decided almost entirely in the Dockerfile.
- A shared checklist makes code review fast and objective instead of taste-driven.
- Most production container incidents trace back to a Dockerfile choice: shell-form CMD, root user, unpinned base, secrets in layers ([§95](Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)).
- Interviews and the DCA exam routinely ask "what is wrong with this Dockerfile?" ([§103](../Part14/Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md)).

## 3. Prerequisites and Dependencies

Requires Dockerfile instruction knowledge ([§17](../Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md) to [§20](../Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)), build context ([§21](../Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)), base images ([§22](../Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md)), multi-stage builds and caching ([§73](../Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md), [§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), BuildKit ([§75](../Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)), build secrets ([§76](../Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)) and security ([§58](../Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md), [§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).

## 4. Architecture / Conceptual Diagram

```text
  Reference layout (multi-stage, cache-friendly, non-root)

  ┌─ syntax directive ───────────────────────────────────────────────┐
  │ # syntax=docker/dockerfile:1                                      │
  ├─ stage: deps ────────────────────────────────────────────────────┤
  │ FROM base@sha256:... AS deps     (pinned)                         │
  │ COPY manifest + lockfile only    ◄── changes rarely               │
  │ RUN --mount=type=cache ... install deps                           │
  ├─ stage: build ───────────────────────────────────────────────────┤
  │ FROM deps AS build                                                │
  │ COPY src/                        ◄── changes often (late)         │
  │ RUN build                                                         │
  ├─ stage: final (minimal runtime) ─────────────────────────────────┤
  │ FROM distroless/slim@sha256:...                                   │
  │ COPY --from=build --chown=app artifact                            │
  │ USER 10001  │ EXPOSE │ HEALTHCHECK │ LABEL │ STOPSIGNAL           │
  │ ENTRYPOINT ["app"]  CMD ["--default"]    (exec form)              │
  └───────────────────────────────────────────────────────────────────┘

  Order rule:  least-changing ──────────────────────────► most-changing
```

- **Stable first, volatile last** keeps cache hits high.
- **Only the final stage ships**; compilers, package managers and test tools stay behind.

## 5. Hands-On

### 5.1 The Checklist

**Base image and reproducibility**

| # | Rule | Protects |
|---|---|---|
| 1 | Start with `# syntax=docker/dockerfile:1` to get current frontend features | correctness |
| 2 | Choose the smallest suitable base (slim, alpine if musl-compatible, distroless, scratch for static binaries) | minimal |
| 3 | Pin the base by version tag and, for releases, by digest (`image:1.27@sha256:...`) | reproducible |
| 4 | Pin OS packages where feasible (`apt-get install pkg=version`) and language dependencies via lockfiles | reproducible |
| 5 | Use `ARG` only for build-time values; pass `ARG` before `FROM` only for base selection | correctness |
| 6 | Use official or verified publisher images; avoid random Hub images | secure |

**Layers and cache**

| # | Rule | Protects |
|---|---|---|
| 7 | Copy dependency manifests and install before copying source | cacheable |
| 8 | Combine `apt-get update` with install in one `RUN`, clean lists in the same layer | minimal |
| 9 | Use `--no-install-recommends` (apt), `--no-cache` (apk), `--no-cache-dir` (pip) | minimal |
| 10 | Use BuildKit cache mounts for package caches instead of leaving caches in layers | cacheable |
| 11 | Maintain a strict `.dockerignore` (`.git`, `node_modules`, `.env`, build output) | cacheable, secure |
| 12 | Prefer `COPY` over `ADD` unless you need tar auto-extraction or a remote URL with checksum | correctness |
| 13 | Order instructions from least to most frequently changing | cacheable |

**Multi-stage and size**

| # | Rule | Protects |
|---|---|---|
| 14 | Use multi-stage builds; the final stage contains only runtime artifacts | minimal |
| 15 | Name stages (`AS build`) and use `COPY --from=` explicitly | correctness |
| 16 | Do not leave build tools, compilers, test dependencies or source in the final image | minimal, secure |
| 17 | Strip debug symbols and use static builds when targeting scratch/distroless | minimal |

**Security**

| # | Rule | Protects |
|---|---|---|
| 18 | Run as a non-root user with a fixed numeric UID (`USER 10001`) | secure |
| 19 | Never put secrets in `ENV`, `ARG` or `COPY`; use `RUN --mount=type=secret` and `--mount=type=ssh` | secure |
| 20 | Use `COPY --chown` and `--chmod` rather than a separate `RUN chown` layer | minimal, secure |
| 21 | Do not install `sudo`, `ssh` servers or shells that the app does not need | secure |
| 22 | Scan the built image and generate an SBOM and provenance in CI | secure |

**Runtime behaviour**

| # | Rule | Protects |
|---|---|---|
| 23 | Use exec form for `ENTRYPOINT` and `CMD` | correct |
| 24 | End wrapper scripts with `exec "$@"`; use an init (`tini`, `--init`) if the app forks | correct |
| 25 | Set `STOPSIGNAL` if the app does not stop on SIGTERM | operable |
| 26 | Define a `HEALTHCHECK` using a tool that exists in the final image | operable |
| 27 | Document ports with `EXPOSE`; remember it does not publish | operable |
| 28 | Add OCI labels (`org.opencontainers.image.source`, `.revision`, `.version`) | operable |
| 29 | Configure the app via environment variables or mounted files; keep one process per container | operable |
| 30 | Log to stdout/stderr, not to files inside the container | operable |

### 5.2 Before and After

```dockerfile
# BEFORE
FROM ubuntu
COPY . /app
WORKDIR /app
RUN apt-get update
RUN apt-get install -y python3 python3-pip curl vim
RUN pip install -r requirements.txt
ENV API_KEY=<your-api-key>
EXPOSE 8000
CMD python3 app.py
```

```dockerfile
# AFTER
# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS build
WORKDIR /src
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim-bookworm
ARG VERSION=dev
LABEL org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.source=https://github.com/acme/app
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
WORKDIR /app
RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*.whl
COPY --chown=app:app src/ ./src/
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["python","-c","import urllib.request as u;u.urlopen('http://127.0.0.1:8000/health')"]
ENTRYPOINT ["python","-m","src.app"]
CMD ["--port","8000"]
```

Differences: pinned slim base, cache-friendly dependency stage, no secret baked in (the key arrives at run time via env or secret file), non-root numeric user, exec form, labels, a probe that does not need curl, and no apt caches.

### 5.3 Automating the Review

```bash
docker run --rm -i hadolint/hadolint < Dockerfile
docker build --check .
docker build -t app:test . && docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro \
  aquasec/trivy image app:test
docker history app:test --no-trunc | head
docker run --rm app:test id
```

```text
Dockerfile:2 DL3006 warning: Always tag the version of an image explicitly
Dockerfile:6 DL3008 warning: Pin versions in apt-get install
Dockerfile:9 DL3025 warning: Use JSON notation for CMD and ENTRYPOINT arguments
uid=10001(app) gid=10001(app) groups=10001(app)
```

(The Docker-socket mount in the Trivy example is for local use only; in CI prefer scanning an exported archive or registry image, see [§81](../Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md).)

### 5.4 Cache-Friendly Ordering Verified

```bash
docker build -t app:1 .
touch src/app.py
docker build -t app:2 . 2>&1 | grep -E 'CACHED|RUN'
```

```text
#7 [build 3/4] RUN pip wheel ...        CACHED
#10 [final 5/6] COPY src/ ./src/        (rebuilt)
```

Only the source layer rebuilds after a code edit; the dependency layer stays cached.

### 5.5 Pinning by Digest

```bash
docker buildx imagetools inspect python:3.12-slim-bookworm --format '{{json .Manifest.Digest}}'
```

```text
"sha256:9b5d..."
```

Use `FROM python:3.12-slim-bookworm@sha256:9b5d...` and let a dependency bot (Renovate, Dependabot) propose digest updates through pull requests.

## 6. Production Usage Notes

- **Two Dockerfiles or targets:** a `dev` target (hot reload, tools) and a `prod` target from the same file via `--target`.
- **Base image refresh policy:** rebuild regularly (weekly or on CVE) even without code changes; pinning by digest needs a bot to move forward.
- **One checklist, enforced in CI:** hadolint plus `docker build --check` as blocking steps, and a policy test on `docker inspect` (User not root, Healthcheck present, labels present).
- **Platform awareness:** build for the target architecture ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)); `FROM --platform=$BUILDPLATFORM` for cross-compiling stages.
- **Image size budget** per service (for example under 150 MB) tracked in CI ([§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)).
- **Tagging:** immutable version tags plus the Git SHA; do not deploy `latest` ([§23](../Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)).
- **Document overrides:** README lists env vars, ports, volumes and the entrypoint contract ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)).

## 7. Security Considerations

- **Non-root by default**; if a port below 1024 is needed, use a high port and map it, or grant only `NET_BIND_SERVICE` ([§59](../Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)).
- **Secrets never touch layers:** `ENV`/`ARG` values are visible in `docker history` and `docker inspect`; deleted files in a later layer still exist in the earlier one.
- **Reduce what an attacker can use:** no shell or package manager in the final image where possible; combine with read-only root filesystem at run time ([§62](../Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)).
- **Supply chain:** pin digests, verify signatures, produce SBOM and provenance attestations ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)).
- **Remote `ADD` URLs** fetch unverified content; use `curl` with a checksum in a build stage or `ADD --checksum=sha256:...`.
- **`.dockerignore` is a security control:** it keeps `.env`, `.git`, SSH keys and cloud credentials out of the context and thus out of layers.

## 8. Common Troubleshooting Scenarios

| Symptom | Cause | Fix |
|---|---|---|
| Every build reinstalls dependencies | `COPY . .` before install, or timestamp-varying input | Copy lockfile first; tighten `.dockerignore` |
| Image 1 GB for a small app | Full base, build tools in final stage, caches left | Multi-stage, slim base, cache mounts, clean in same layer |
| `apt-get install` fails with 404 | Stale `update` layer cached separately | Single `RUN apt-get update && apt-get install ...` |
| App cannot write at run time as non-root | Directories owned by root | `COPY --chown`, or create dirs with correct owner |
| `exec format error` | Wrong architecture or CRLF script | Match `--platform`; normalize line endings |
| Health check always fails | `curl`/`wget` missing in final image | Use language runtime probe or a tiny static binary |
| Non-reproducible builds | Unpinned base, `latest`, unpinned packages | Pin digests and lockfiles |
| Build-time secret visible in history | Used `ARG`/`ENV` | `RUN --mount=type=secret`, rotate the leaked value |
| Slow context upload | Large directories sent | `.dockerignore`, build from a subdirectory |

## 9. Best Practices

- Treat the checklist as a living document owned by the platform team and versioned with your templates.
- Provide golden Dockerfile templates per language so teams start compliant.
- Lint locally (pre-commit) and in CI; fail on high-severity findings.
- Keep Dockerfiles short and readable; comment the "why" of non-obvious lines (pins, workarounds).
- Review the final image, not only the Dockerfile: `docker history`, `dive`, `docker inspect`, `docker run ... id` ([§25](../Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)).
- Rebuild and rescan on a schedule, not only when code changes.
- Prefer composition (multi-stage, copy artifacts) over a single mega-`RUN`.
- Keep one concern per image: one main process, configuration from outside, state in volumes ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)).

## 10. Common Anti-Patterns / Mistakes

- Treating the checklist as a one-time audit instead of an automated gate.
- Pinning versions but never updating them, which freezes known CVEs in place.
- Over-optimizing size with alpine when the app needs glibc, causing runtime bugs.
- Cramming everything into one `RUN` so that cache never helps, or splitting into dozens of tiny layers that duplicate cleanup.
- Using multi-stage builds but copying the entire build directory (`COPY --from=build /src /app`).
- Applying `USER` before installing packages or creating directories, then fighting permissions.
- Copying the checklist without understanding it, for example `HEALTHCHECK` with a tool absent from the image.

## 11. Interview Questions

**🎯 Beginner:** _"Why do we copy `package.json` and run `npm ci` before copying the rest of the source?"_
**Model answer:** Docker caches each layer and invalidates a layer when its inputs or any earlier layer change. Dependencies change rarely and source changes constantly, so installing dependencies in a layer that depends only on the manifest and lockfile lets later builds reuse that expensive layer. If you `COPY . .` first, any source edit invalidates the install step and downloads everything again. The rule generalizes to ordering instructions from least to most frequently changing.
_What the interviewer is probing for:_ Understanding of layer cache invalidation and instruction ordering.

**🎯 Intermediate:** _"Review this: `FROM node:latest`, `COPY . .`, `RUN npm install`, `ENV TOKEN=abc`, `CMD npm start`. List what you would change."_
**Model answer:** Pin the base to a version (and digest for releases) instead of `latest`; add `.dockerignore` and copy lockfiles first for cache; use `npm ci --omit=dev`; move to a multi-stage build with a slim or distroless runtime; remove the token from `ENV` and inject it at run time or use a build secret if needed at build; add a non-root `USER`; switch to exec-form `CMD ["node","server.js"]` so signals reach Node and `npm` is not PID 1; add a `HEALTHCHECK` and labels. I would then lint with hadolint and scan with Trivy.
_What the interviewer is probing for:_ Breadth across cache, size, secrets, users and signals, with prioritization.

**🎯 Senior:** _"Your builds are not reproducible: the same commit produces different images on different days. How do you fix it?"_
**Model answer:** Identify the moving inputs: unpinned base tags, `apt-get`/`apk` package versions, language dependencies without lockfiles, network downloads without checksums, timestamps and build-time metadata. Pin the base by digest, use lockfiles (`npm ci`, `pip --require-hashes`, `go.sum`), pin or snapshot OS packages (snapshot.debian.org or a mirror), verify downloads with checksums, and set `SOURCE_DATE_EPOCH` with BuildKit's `rewrite-timestamp` output option for deterministic layer timestamps. Keep dependency updates flowing through a bot so pinning does not freeze vulnerabilities, and compare digests of two builds in CI to prove reproducibility.
_What the interviewer is probing for:_ Systematic hunting of nondeterminism and balancing pinning with patching.

**🎯 Architect:** _"You own 200 services built by 40 teams. How do you roll out a Dockerfile standard without blocking delivery?"_
**Model answer:** Ship paved-road assets: language-specific golden templates, a hardened and regularly rebuilt base image set, and a shared CI action that runs hadolint, `docker build --check`, a policy check on image config (non-root, health check, labels, size budget), a scan and SBOM/signature step. Roll out in phases: report-only, then warn, then block for new services, then for existing ones with exceptions that expire. Measure compliance and build times on a dashboard, offer migration PRs generated by a bot, and keep the standard small enough (about 30 rules, tagged by severity) to be adopted. Review it quarterly against incidents and BuildKit releases.
_What the interviewer is probing for:_ Governance via automation and incremental adoption rather than mandates and documents.

## 12. Common Misconceptions

- "Smaller is always better." Correctness and debuggability matter; alpine's musl and shell-less images have costs.
- "Pinning a tag is immutable." Tags can move; only digests are immutable.
- "Deleting a file in a later layer removes it from the image." It still exists in the earlier layer and can be extracted.
- "`EXPOSE` opens the port." It documents only.
- "`.dockerignore` only speeds up builds." It also prevents secret leakage.
- "Multi-stage builds are only for compiled languages." They also separate dev dependencies for interpreted languages.

## 13. 🔑 Key Takeaways

- Order instructions from least to most volatile and install dependencies from lockfiles first.
- Pin bases (digest for releases), use multi-stage builds, and ship only runtime artifacts.
- Non-root numeric `USER`, no secrets in layers, strict `.dockerignore`.
- Exec form, `exec "$@"`, init when needed, `STOPSIGNAL`, a working `HEALTHCHECK`.
- Automate: hadolint, `docker build --check`, scan, SBOM, config policy checks.
- Review the built image, not just the Dockerfile.

## 14. Related Concepts & What's Next

Related: build mechanics ([§24](../Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)), caching ([§74](../Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md)), size ([§77](../Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)), reproducibility ([§78](../Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)), code-review drills ([§103](../Part14/Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md)). Next, [§95](Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md) examines the opposite side: the common anti-patterns, with the mechanism by which each one hurts.

**Next Section:** [§95](Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md) — `Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md`
